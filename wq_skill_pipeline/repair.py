from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import read_jsonl, stable_hash, write_jsonl, write_text


PRIORITY = {
    "hard_block": 10,
    "correlation_similarity": 20,
    "turnover_density": 30,
    "coverage_concentration": 40,
    "unit_platform": 50,
    "metric_near_pass": 60,
}

ROUTES = {
    "hard_block": ["community::submission_gate", "community_failure::template_clone_blocker"],
    "correlation_similarity": [
        "community::near_pass_repair",
        "community_failure::correlation_near_pass_or_highscore_repair",
    ],
    "turnover_density": ["community::operation_attribution", "community_failure::turnover_density_repair"],
    "coverage_concentration": [
        "community::operation_attribution",
        "community_failure::low_coverage_concentration_repair",
    ],
    "unit_platform": ["community::operation_attribution", "community_failure::operator_platform_unit_probe"],
    "metric_near_pass": ["community::near_pass_repair", "community_failure::metric_near_pass_overlay_repair"],
}

REPAIR_ACTIONS = {
    "hard_block": "Do not mutate this candidate directly. Block unchanged template/private/unsupported variants and restart from a transformed skeleton.",
    "correlation_similarity": "Preserve the thesis only if score is strong; run a small settings grid, then shift field/operator family if similarity remains high.",
    "turnover_density": "Tune smoothing, decay/trade density, and breadth together; avoid changing only one lookback window.",
    "coverage_concentration": "Add a broad high-coverage leg or reduce sparse-field dominance before rerunning checks.",
    "unit_platform": "Run tiny legal-input probes and normalize with rank/scale/ratio before spending full simulation budget.",
    "metric_near_pass": "Preserve the core thesis, reduce crowded trunk exposure, add a broad overlay, and run a fresh precheck.",
}

AVOID_ACTIONS = {
    "hard_block": "Do not submit, simulate, or publish direct forum templates or unsupported operators.",
    "correlation_similarity": "Do not rely on single-window tweaks for correlation failures.",
    "turnover_density": "Do not tune turnover without checking density and coverage together.",
    "coverage_concentration": "Do not add more sparse fields from the same family.",
    "unit_platform": "Do not assume operator support from forum text alone.",
    "metric_near_pass": "Do not abandon a high-score near-pass parent before trying low-risk overlay repairs.",
}


def load_ledger_records(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_dir():
            for child in path.rglob("*.jsonl"):
                rows.extend(read_jsonl(child))
            for child in path.rglob("*.json"):
                rows.extend(_read_json_records(child))
        elif path.suffix.lower() == ".jsonl":
            rows.extend(read_jsonl(path))
        elif path.suffix.lower() == ".json":
            rows.extend(_read_json_records(path))
    return rows


def build_repair_suggestions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for record in records:
        bucket = _failure_bucket(record)
        if not bucket:
            continue
        signals = _failure_signals(record, bucket)
        suggestion = {
            "schema_version": 1,
            "suggestion_id": f"repair::{stable_hash({'record': _source_ref(record), 'bucket': bucket, 'signals': signals})}",
            "source_ref": _source_ref(record),
            "priority": PRIORITY[bucket],
            "failure_bucket": bucket,
            "failure_signals": signals,
            "recommended_repair": REPAIR_ACTIONS[bucket],
            "avoid": AVOID_ACTIONS[bucket],
            "recheck_evidence": _recheck_evidence(bucket),
            "community_skill_route": ROUTES[bucket],
        }
        suggestions.append(suggestion)
    return sorted(suggestions, key=lambda row: (row["priority"], row["suggestion_id"]))


def write_repair_suggestions(suggestions: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    jsonl_path = output_dir / "near_pass_repair_suggestions.jsonl"
    markdown_path = output_dir / "near_pass_repair_playbook.md"
    write_jsonl(jsonl_path, suggestions)
    write_text(markdown_path, render_repair_playbook(suggestions))
    return {"repair_suggestions_jsonl": str(jsonl_path), "repair_playbook_markdown": str(markdown_path)}


def render_repair_playbook(suggestions: list[dict[str, Any]]) -> str:
    lines = [
        "# Near-Pass Repair Playbook",
        "",
        "Suggestions are sorted by deterministic failure-type priority, not by free-form LLM ranking.",
        "",
        "| Priority | Bucket | Source | Repair Route | First Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in suggestions:
        lines.append(
            "| {priority} | {bucket} | {source} | {route} | {action} |".format(
                priority=row["priority"],
                bucket=row["failure_bucket"],
                source=row["source_ref"],
                route=", ".join(row["community_skill_route"]),
                action=row["recommended_repair"],
            )
        )
    if not suggestions:
        lines.append("| - | none | - | - | No near-pass or failed-check records found. |")
    lines.extend(["", "## Boundary", ""])
    lines.append("- The playbook explains repair direction; it does not generate submit-ready expressions.")
    lines.append("- Fresh checks are required before any human submit review.")
    return "\n".join(lines) + "\n"


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("records", "rows", "candidates", "results", "alphas", "items"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [value]
    return []


def _failure_bucket(record: dict[str, Any]) -> str:
    text = " ".join(str(value).lower() for value in record.values() if isinstance(value, (str, int, float, list, dict)))
    flags: set[str] = set()
    for key in ("risk_flags", "failure_tags"):
        value = record.get(key)
        if isinstance(value, list):
            flags.update(str(flag).lower() for flag in value)
    combined = " ".join(sorted(flags)) + " " + text
    if any(token in combined for token in ["private", "template_clone", "forum_direct", "unsupported", "hard_block"]):
        return "hard_block"
    if any(token in combined for token in ["correlation", "similarity", "self_corr", "prod_corr"]):
        return "correlation_similarity"
    if any(token in combined for token in ["turnover", "density", "trade_when"]):
        return "turnover_density"
    if any(token in combined for token in ["coverage", "concentration", "sparse", "low_coverage"]):
        return "coverage_concentration"
    if any(token in combined for token in ["unit", "operator", "platform", "legal"]):
        return "unit_platform"
    if any(token in combined for token in ["near_pass", "near pass", "fitness", "sharpe"]):
        return "metric_near_pass"
    fitness = _float(record.get("fitness"))
    if fitness is not None and 0.8 <= fitness < 1.05:
        return "metric_near_pass"
    return ""


def _failure_signals(record: dict[str, Any], bucket: str) -> list[str]:
    signals = [bucket]
    for key in ("risk_flags", "failure_tags", "community_skill_tags"):
        value = record.get(key)
        if isinstance(value, list):
            signals.extend(str(item) for item in value[:8])
    for key in ("fitness", "sharpe", "turnover", "coverage", "self_corr", "prod_corr", "reason"):
        if key in record:
            signals.append(f"{key}={record[key]}")
    return list(dict.fromkeys(signals))


def _source_ref(record: dict[str, Any]) -> str:
    for key in ("alpha_id", "candidate_id", "id", "path", "source", "tag"):
        if record.get(key):
            return f"ledger::{stable_hash(str(record[key]))}"
    return f"ledger::{stable_hash(record)}"


def _recheck_evidence(bucket: str) -> list[str]:
    common = ["fresh platform check", "latest correlation check", "presubmit gate review"]
    if bucket == "unit_platform":
        return ["tiny legal-input probe", "operator support check", *common]
    if bucket == "coverage_concentration":
        return ["coverage distribution", "weight concentration report", *common]
    if bucket == "turnover_density":
        return ["turnover report", "trade density report", *common]
    return common


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

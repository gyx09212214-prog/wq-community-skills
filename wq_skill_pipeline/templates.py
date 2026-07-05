from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .io_utils import stable_hash, write_jsonl, write_text
from .privacy import looks_like_complete_expression, redact_text


OPERATOR_TOKENS = [
    "rank",
    "ts_rank",
    "ts_corr",
    "ts_mean",
    "ts_delta",
    "ts_std_dev",
    "trade_when",
    "group_rank",
    "group_neutralize",
    "decay_linear",
    "scale",
    "winsorize",
    "humpdecay",
]

FIELD_FAMILY_KEYWORDS = {
    "liquidity_microstructure": ["volume", "vwap", "liquidity", "turnover", "adv", "dollar volume"],
    "fundamental_value_quality": ["sales", "revenue", "earnings", "eps", "cashflow", "book", "value", "quality"],
    "sentiment_revision": ["sentiment", "news", "analyst", "revision", "estimate", "guidance"],
    "price_momentum": ["price", "return", "momentum", "reversal", "close", "open"],
    "coverage_missingness": ["coverage", "missing", "sparse", "null", "availability"],
}

USE_CASE_KEYWORDS = {
    "near_pass_repair": ["near pass", "almost pass", "close to pass", "fitness", "sharpe"],
    "correlation_repair": ["correlation", "similarity", "self corr", "prod corr"],
    "turnover_repair": ["turnover", "density", "trade_when"],
    "coverage_repair": ["coverage", "concentration", "sparse", "missing"],
    "unit_platform_probe": ["unit", "operator", "unsupported", "platform"],
}


def build_template_catalog(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        text = _record_text(record)
        if not text.strip():
            continue
        operators = _operators(text)
        families = _field_families(text)
        use_cases = _use_cases(text)
        complete_expression = looks_like_complete_expression(text)
        if not operators and not families and not use_cases and not complete_expression:
            continue
        skeleton = _operator_skeleton(operators)
        source_ref = _source_ref(record)
        key = stable_hash({"skeleton": skeleton, "families": families, "use_cases": use_cases, "source": source_ref})
        if key in seen:
            continue
        seen.add(key)
        risk_flags = ["template_skeleton"]
        if complete_expression:
            risk_flags.append("private_or_public_template_risk")
        if "correlation_repair" in use_cases:
            risk_flags.append("correlation_risk")
        if "turnover_repair" in use_cases:
            risk_flags.append("turnover_density_risk")
        compact_evidence = (
            "Complete expression redacted; retained as operator skeleton and risk flags only."
            if complete_expression
            else redact_text(text)
        )
        title = "community template" if looks_like_complete_expression(str(record.get("title") or "")) else str(record.get("title") or record.get("name") or "community template")
        catalog.append(
            {
                "schema_version": 1,
                "template_id": f"template::{key}",
                "source_ref": source_ref,
                "title": redact_text(title, max_chars=120),
                "field_families": families or ["unknown_family"],
                "operator_skeleton": skeleton,
                "use_cases": use_cases or ["template_acquisition"],
                "risk_flags": sorted(set(risk_flags)),
                "recommended_transforms": _recommended_transforms(families, use_cases, complete_expression),
                "blocked_outputs": ["complete_expression", "raw_forum_quote", "submit_ready_alpha"],
                "compact_evidence": compact_evidence,
            }
        )
    return catalog


def write_template_catalog(catalog: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    jsonl_path = output_dir / "template_catalog.redacted.jsonl"
    markdown_path = output_dir / "template_catalog.md"
    write_jsonl(jsonl_path, catalog)
    write_text(markdown_path, render_template_catalog_markdown(catalog))
    return {"template_catalog_jsonl": str(jsonl_path), "template_catalog_markdown": str(markdown_path)}


def render_template_catalog_markdown(catalog: list[dict[str, Any]]) -> str:
    lines = [
        "# Template Skeleton Catalog",
        "",
        "Public-safe template skeletons extracted from community/forum evidence. Complete expressions and raw quotes are not emitted.",
        "",
        "| Template | Families | Skeleton | Use Cases | Risk Flags |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in catalog:
        lines.append(
            "| {template} | {families} | {skeleton} | {use_cases} | {flags} |".format(
                template=row["template_id"],
                families=", ".join(row["field_families"]),
                skeleton=row["operator_skeleton"],
                use_cases=", ".join(row["use_cases"]),
                flags=", ".join(row["risk_flags"]),
            )
        )
    if not catalog:
        lines.append("| none | - | - | - | - |")
    lines.extend(["", "## Recommended Transform Defaults", ""])
    lines.append("- Treat every template as grammar, not as a submit-ready alpha.")
    lines.append("- Require a field-family or operator-family change before simulation.")
    lines.append("- Add an orthogonal overlay and rerun fresh checks before any submit review.")
    return "\n".join(lines) + "\n"


def _record_text(record: dict[str, Any]) -> str:
    parts = [
        str(record.get("title") or ""),
        str(record.get("body") or ""),
        str(record.get("text") or ""),
        str(record.get("content") or ""),
        str(record.get("comment") or ""),
    ]
    return "\n".join(part for part in parts if part)


def _source_ref(record: dict[str, Any]) -> str:
    source = record.get("source_id") or record.get("id") or record.get("post_id") or record.get("url") or _record_text(record)[:80]
    return f"source::{stable_hash(str(source))}"


def _operators(text: str) -> list[str]:
    lowered = text.lower()
    hits = []
    for token in OPERATOR_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            hits.append(token)
    return hits


def _field_families(text: str) -> list[str]:
    lowered = text.lower()
    families = []
    for family, keywords in FIELD_FAMILY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            families.append(family)
    return families


def _use_cases(text: str) -> list[str]:
    lowered = text.lower()
    cases = []
    for use_case, keywords in USE_CASE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            cases.append(use_case)
    return cases


def _operator_skeleton(operators: list[str]) -> str:
    if not operators:
        return "conceptual_template"
    counts = Counter(operators)
    ordered = sorted(counts, key=lambda item: (-counts[item], operators.index(item)))
    return " -> ".join(ordered[:5])


def _recommended_transforms(families: list[str], use_cases: list[str], complete_expression: bool) -> list[str]:
    actions = ["change field family", "change operator family", "add orthogonal overlay", "run fresh precheck"]
    if complete_expression:
        actions.insert(0, "block unchanged template")
    if "correlation_repair" in use_cases:
        actions.append("shift to lower-overlap field family")
    if "turnover_repair" in use_cases:
        actions.append("tune smoothing and trade density together")
    if "coverage_missingness" in families:
        actions.append("add broad high-coverage leg")
    return list(dict.fromkeys(actions))

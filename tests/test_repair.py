from __future__ import annotations

from pathlib import Path

from wq_skill_pipeline.io_utils import read_jsonl
from wq_skill_pipeline.repair import build_repair_suggestions


def test_repair_suggestions_follow_failure_priority() -> None:
    suggestions = build_repair_suggestions(
        [
            {"candidate_id": "metric", "risk_flags": ["metric_near_pass"], "fitness": 0.98},
            {"candidate_id": "corr", "risk_flags": ["correlation_risk"], "self_corr": 0.72},
            {"candidate_id": "hard", "risk_flags": ["template_clone_risk"]},
            {"candidate_id": "unit", "risk_flags": ["unit_check"]},
        ]
    )

    assert [row["failure_bucket"] for row in suggestions] == [
        "hard_block",
        "correlation_similarity",
        "unit_platform",
        "metric_near_pass",
    ]
    assert suggestions[0]["community_skill_route"][0] == "community::submission_gate"


def test_repair_suggestion_contains_required_fields() -> None:
    suggestion = build_repair_suggestions(
        [{"candidate_id": "turnover", "risk_flags": ["turnover_density_risk"], "turnover": 0.8}]
    )[0]

    assert suggestion["recommended_repair"]
    assert suggestion["avoid"]
    assert "fresh platform check" in suggestion["recheck_evidence"]
    assert "community_failure::turnover_density_repair" in suggestion["community_skill_route"]


def test_jsonl_reader_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text('\ufeff{"candidate_id":"bom","risk_flags":["metric_near_pass"]}\n', encoding="utf-8")

    assert read_jsonl(path)[0]["candidate_id"] == "bom"

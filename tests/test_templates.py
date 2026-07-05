from __future__ import annotations

from wq_skill_pipeline.privacy import scan_text
from wq_skill_pipeline.templates import build_template_catalog


def test_template_extraction_redacts_complete_expression() -> None:
    catalog = build_template_catalog(
        [
            {
                "id": "post-1",
                "title": "complete expression example",
                "body": "Try rank(ts_rank(volume, 20)) when fitness is near pass, but treat it as template only.",
            }
        ]
    )

    assert len(catalog) == 1
    row = catalog[0]
    assert "private_or_public_template_risk" in row["risk_flags"]
    assert row["operator_skeleton"] == "rank -> ts_rank"
    assert "rank(" not in row["compact_evidence"]
    assert not scan_text(row["compact_evidence"])


def test_template_extraction_builds_skeleton_without_expression() -> None:
    catalog = build_template_catalog(
        [
            {
                "id": "post-2",
                "title": "coverage repair",
                "body": "Sparse coverage template uses rank and group neutralize ideas for cashflow quality.",
            }
        ]
    )

    assert catalog[0]["field_families"] == ["fundamental_value_quality", "coverage_missingness"]
    assert "coverage_repair" in catalog[0]["use_cases"]

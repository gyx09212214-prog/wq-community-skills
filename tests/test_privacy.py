from __future__ import annotations

from pathlib import Path

import pytest

from wq_skill_pipeline.pipeline import export_public
from wq_skill_pipeline.privacy import PrivacyScanError, scan_text


def test_privacy_scan_flags_expression_and_secret() -> None:
    findings = scan_text('{"cookie": "abc"}\nrank(ts_rank(volume, 20))')
    kinds = {finding.kind for finding in findings}
    assert "secret_or_credential" in kinds
    assert "possible_alpha_expression" in kinds


def test_export_public_fails_closed_on_expression(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "skills").mkdir(parents=True)
    (run_dir / "repair").mkdir()
    (run_dir / "review").mkdir()
    required = {
        run_dir / "skills" / "template_catalog.redacted.jsonl": '{"x": "rank(ts_rank(volume, 20))"}\n',
        run_dir / "skills" / "template_catalog.md": "# ok\n",
        run_dir / "skills" / "community_skill_memory.redacted.jsonl": "{}\n",
        run_dir / "skills" / "submission_policy.redacted.json": "{}\n",
        run_dir / "repair" / "near_pass_repair_suggestions.jsonl": "{}\n",
        run_dir / "repair" / "near_pass_repair_playbook.md": "# ok\n",
        run_dir / "review" / "review_report.html": "<html></html>\n",
    }
    for path, text in required.items():
        path.write_text(text, encoding="utf-8")

    with pytest.raises(PrivacyScanError):
        export_public(run_dir=run_dir, public_output=tmp_path / "public")
    assert not (tmp_path / "public").exists()

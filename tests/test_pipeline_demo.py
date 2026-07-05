from __future__ import annotations

import json
from pathlib import Path

from wq_skill_pipeline.pipeline import run_demo


def test_demo_runs_full_synthetic_pipeline(tmp_path: Path) -> None:
    result = run_demo(runs_root=tmp_path / "runs", public_output=tmp_path / "public")

    assert result["ok"] is True
    run_dir = Path(result["run_dir"])
    public_dir = Path(result["public_output"])
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "skills" / "template_catalog.redacted.jsonl").is_file()
    assert (run_dir / "repair" / "near_pass_repair_suggestions.jsonl").is_file()
    assert (public_dir / "review_report.html").is_file()
    assert (public_dir / "manifest.json").is_file()

    manifest = json.loads((public_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["privacy_scan"]["ok"] is True
    assert "template_catalog.redacted" in manifest["files"]


def test_demo_manifest_records_llm_boundary(tmp_path: Path) -> None:
    result = run_demo(
        runs_root=tmp_path / "runs",
        public_output=tmp_path / "public",
        allow_raw_llm=True,
        model="test-model",
    )
    manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["allow_raw_llm"] is True
    assert manifest["llm"]["allow_raw_llm"] is True
    assert manifest["llm"]["model"] == "test-model"
    assert manifest["llm"]["prompt_hash"]

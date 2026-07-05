from __future__ import annotations

import json
from pathlib import Path

from wq_skill_pipeline.cli import main


def test_cli_demo_parses_and_runs(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(["demo", "--workspace", str(tmp_path / "runs"), "--public-output", str(tmp_path / "public")])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True


def test_cli_repair_suggest_from_file(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"candidate_id":"a","risk_flags":["correlation_risk"]}\n', encoding="utf-8")
    output = tmp_path / "out"

    code = main(["repair", "suggest", "--ledger-root", str(ledger), "--output-dir", str(output)])
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["suggestions"] == 1
    assert (output / "near_pass_repair_suggestions.jsonl").is_file()

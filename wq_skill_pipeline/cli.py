from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .community import (
    DEFAULT_BASE_URL,
    DEFAULT_COMMENTS_PATH_TEMPLATE,
    DEFAULT_POSTS_PATH,
    export_community_readonly,
    save_login_state,
)
from .io_utils import read_jsonl, write_json, write_jsonl
from .paths import default_runs_root, default_state_path
from .pipeline import export_public, run_demo, run_live
from .privacy import PrivacyScanError
from .repair import build_repair_suggestions, load_ledger_records, write_repair_suggestions
from .templates import build_template_catalog, write_template_catalog


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except PrivacyScanError as exc:
        print("Privacy scan failed; public artifacts were not exported.", file=sys.stderr)
        print(json.dumps([finding.to_dict() for finding in exc.findings], ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WQ community template and near-pass repair skill pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the live readonly pipeline")
    _add_common_run_args(run)
    _add_live_args(run)
    run.add_argument("--ledger-root", action="append", default=[], help="Local worldquant-harness ledger/report dir or file")
    run.add_argument("--no-auto-login", action="store_true", help="Do not open browser when storage state is missing")
    run.set_defaults(func=_cmd_run)

    login = sub.add_parser("login", help="Save Playwright storage state for readonly Community fetch")
    login.add_argument("--state-path", default=str(default_state_path()))
    login.add_argument("--login-url", default=DEFAULT_BASE_URL)
    login.add_argument("--timeout-ms", type=int, default=120_000)
    login.set_defaults(func=_cmd_login)

    demo = sub.add_parser("demo", help="Run a full synthetic no-credential demo")
    _add_common_run_args(demo)
    demo.set_defaults(func=_cmd_demo)

    doctor = sub.add_parser("doctor", help="Check local environment and optional capabilities")
    doctor.add_argument("--state-path", default=str(default_state_path()))
    doctor.set_defaults(func=_cmd_doctor)

    export = sub.add_parser("export-public", help="Export public-safe artifacts from an existing run")
    export.add_argument("--run-dir", required=True)
    export.add_argument("--public-output", required=True)
    export.set_defaults(func=_cmd_export_public)

    templates = sub.add_parser("templates", help="Template skeleton commands")
    template_sub = templates.add_subparsers(dest="templates_command", required=True)
    fetch = template_sub.add_parser("fetch", help="Fetch or read community records and write template skeleton catalog")
    fetch.add_argument("--input-posts", default="")
    fetch.add_argument("--input-comments", default="")
    fetch.add_argument("--output-dir", required=True)
    _add_live_args(fetch)
    fetch.set_defaults(func=_cmd_templates_fetch)

    repair = sub.add_parser("repair", help="Near-pass repair commands")
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)
    suggest = repair_sub.add_parser("suggest", help="Read local ledger/check artifacts and write repair suggestions")
    suggest.add_argument("--ledger-root", action="append", default=[], help="Ledger/report dir or JSON/JSONL file")
    suggest.add_argument("--output-dir", required=True)
    suggest.set_defaults(func=_cmd_repair_suggest)
    return parser


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=str(default_runs_root()), help="Run storage root")
    parser.add_argument("--public-output", default="", help="Exact public output directory; default is artifacts/public/<run_id>")
    parser.add_argument("--no-public-output", action="store_true")
    parser.add_argument("--model", default=os.environ.get("WQ_SKILL_MODEL", ""))
    parser.add_argument("--allow-raw-llm", action="store_true")


def _add_live_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-path", default=str(default_state_path()))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--posts-path", default=DEFAULT_POSTS_PATH)
    parser.add_argument("--comments-path-template", default=DEFAULT_COMMENTS_PATH_TEMPLATE)
    parser.add_argument("--max-posts", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)


def _cmd_run(args: argparse.Namespace) -> dict[str, Any]:
    state_path = Path(args.state_path).expanduser()
    if not state_path.is_file():
        if args.no_auto_login:
            raise RuntimeError(f"missing Playwright storage state: {state_path}. Run `python -m wq_skill_pipeline login` first.")
        save_login_state(state_path, login_url=args.base_url)
    ledger_paths = [Path(value).expanduser() for value in args.ledger_root] or _default_ledger_paths()
    return run_live(
        runs_root=Path(args.workspace).expanduser(),
        state_path=state_path,
        public_output=Path(args.public_output).expanduser() if args.public_output else None,
        write_public=not args.no_public_output,
        ledger_paths=ledger_paths,
        allow_raw_llm=args.allow_raw_llm,
        model=args.model,
        base_url=args.base_url,
        posts_path=args.posts_path,
        comments_path_template=args.comments_path_template,
        max_posts=max(1, args.max_posts),
        max_pages=max(1, args.max_pages),
        limit=max(1, args.limit),
        sleep_seconds=max(0.0, args.sleep_seconds),
    )


def _cmd_login(args: argparse.Namespace) -> dict[str, Any]:
    path = save_login_state(Path(args.state_path).expanduser(), login_url=args.login_url, timeout_ms=max(1000, args.timeout_ms))
    return {"ok": True, "state_path": str(path)}


def _cmd_demo(args: argparse.Namespace) -> dict[str, Any]:
    return run_demo(
        runs_root=Path(args.workspace).expanduser(),
        public_output=Path(args.public_output).expanduser() if args.public_output else None,
        write_public=not args.no_public_output,
        allow_raw_llm=args.allow_raw_llm,
        model=args.model,
    )


def _cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "python": sys.version.split()[0],
        "state_path_exists": Path(args.state_path).expanduser().is_file(),
        "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "wq_skill_model": os.environ.get("WQ_SKILL_MODEL", ""),
        "default_runs_root": str(default_runs_root()),
    }
    try:
        import playwright  # type: ignore  # noqa: F401

        checks["playwright_installed"] = True
    except ImportError:
        checks["playwright_installed"] = False
    try:
        import worldquant_harness  # type: ignore  # noqa: F401

        checks["worldquant_harness_adapter_available"] = True
    except ImportError:
        checks["worldquant_harness_adapter_available"] = False
    checks["ok_for_demo"] = True
    checks["ok_for_live"] = checks["state_path_exists"] and checks["playwright_installed"]
    return checks


def _cmd_export_public(args: argparse.Namespace) -> dict[str, Any]:
    return export_public(run_dir=Path(args.run_dir).expanduser(), public_output=Path(args.public_output).expanduser())


def _cmd_templates_fetch(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    records = []
    if args.input_posts:
        records.extend(read_jsonl(Path(args.input_posts).expanduser()))
    if args.input_comments:
        records.extend(read_jsonl(Path(args.input_comments).expanduser()))
    if not records:
        raw_dir = output_dir / "_raw_readonly"
        manifest = export_community_readonly(
            state_path=Path(args.state_path).expanduser(),
            output_dir=raw_dir,
            base_url=args.base_url,
            posts_path=args.posts_path,
            comments_path_template=args.comments_path_template,
            max_posts=max(1, args.max_posts),
            max_pages=max(1, args.max_pages),
            limit=max(1, args.limit),
            sleep_seconds=max(0.0, args.sleep_seconds),
        )
        records.extend(read_jsonl(raw_dir / "posts.jsonl"))
        records.extend(read_jsonl(raw_dir / "comments.jsonl"))
    catalog = build_template_catalog(records)
    files = write_template_catalog(catalog, output_dir)
    return {"ok": True, "templates": len(catalog), "files": files}


def _cmd_repair_suggest(args: argparse.Namespace) -> dict[str, Any]:
    paths = [Path(value).expanduser() for value in args.ledger_root] or _default_ledger_paths()
    records = load_ledger_records(paths)
    suggestions = build_repair_suggestions(records)
    files = write_repair_suggestions(suggestions, Path(args.output_dir).expanduser())
    return {"ok": True, "records": len(records), "suggestions": len(suggestions), "files": files}


def _default_ledger_paths() -> list[Path]:
    candidates = []
    root = os.environ.get("WQ_HARNESS_ROOT")
    if root:
        candidates.append(Path(root).expanduser() / "reports")
    default = Path("D:/code/worldquant-harness/reports")
    if default.exists():
        candidates.append(default)
    return candidates


def _write_debug(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, value)

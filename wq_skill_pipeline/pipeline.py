from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .community import export_community_readonly, synthetic_community_records
from .io_utils import ensure_dir, file_hash, read_jsonl, stable_hash, write_json, write_jsonl
from .llm import build_llm_audit
from .paths import RunPaths, make_run_paths
from .privacy import PrivacyScanError, scan_file
from .repair import build_repair_suggestions, load_ledger_records, write_repair_suggestions
from .reports import write_review_report
from .skills import build_skill_memory, build_submission_policy, write_skill_artifacts
from .templates import build_template_catalog, write_template_catalog


def run_demo(
    *,
    runs_root: Path,
    public_output: Path | None = None,
    write_public: bool = True,
    allow_raw_llm: bool = False,
    model: str = "",
) -> dict[str, Any]:
    paths = make_run_paths(runs_root, prefix="demo")
    if write_public and public_output is None:
        public_output = Path.cwd() / "artifacts" / "public" / paths.run_id
    posts, comments = synthetic_community_records()
    ledger = synthetic_ledger_records()
    ensure_dir(paths.raw_dir)
    write_jsonl(paths.raw_dir / "posts.jsonl", posts)
    write_jsonl(paths.raw_dir / "comments.jsonl", comments)
    write_jsonl(paths.normalized_dir / "ledger.synthetic.jsonl", ledger)
    return build_run_outputs(
        paths=paths,
        community_records=posts + comments,
        ledger_records=ledger,
        mode="demo",
        allow_raw_llm=allow_raw_llm,
        model=model,
        public_output=public_output,
        source_manifest={"mode": "synthetic_demo", "posts": len(posts), "comments": len(comments)},
    )


def run_live(
    *,
    runs_root: Path,
    state_path: Path,
    public_output: Path | None = None,
    write_public: bool = True,
    ledger_paths: list[Path] | None = None,
    allow_raw_llm: bool = False,
    model: str = "",
    base_url: str,
    posts_path: str,
    comments_path_template: str,
    max_posts: int,
    max_pages: int,
    limit: int,
    sleep_seconds: float,
) -> dict[str, Any]:
    paths = make_run_paths(runs_root, prefix="run")
    if write_public and public_output is None:
        public_output = Path.cwd() / "artifacts" / "public" / paths.run_id
    manifest = export_community_readonly(
        state_path=state_path,
        output_dir=paths.raw_dir,
        base_url=base_url,
        posts_path=posts_path,
        comments_path_template=comments_path_template,
        max_posts=max_posts,
        max_pages=max_pages,
        limit=limit,
        sleep_seconds=sleep_seconds,
    )
    posts = read_jsonl(paths.raw_dir / "posts.jsonl")
    comments = read_jsonl(paths.raw_dir / "comments.jsonl")
    ledger_records = load_ledger_records(ledger_paths or [])
    return build_run_outputs(
        paths=paths,
        community_records=posts + comments,
        ledger_records=ledger_records,
        mode="live_readonly",
        allow_raw_llm=allow_raw_llm,
        model=model,
        public_output=public_output,
        source_manifest=manifest,
    )


def build_run_outputs(
    *,
    paths: RunPaths,
    community_records: list[dict[str, Any]],
    ledger_records: list[dict[str, Any]],
    mode: str,
    allow_raw_llm: bool,
    model: str,
    public_output: Path | None,
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
    ensure_dir(paths.skills_dir)
    ensure_dir(paths.repair_dir)
    ensure_dir(paths.review_dir)
    template_catalog = build_template_catalog(community_records)
    repair_suggestions = build_repair_suggestions(ledger_records)
    skill_memory = build_skill_memory(template_catalog, repair_suggestions)
    submission_policy = build_submission_policy(template_catalog, repair_suggestions)
    llm_audit = build_llm_audit(template_catalog + repair_suggestions, model=model, allow_raw_llm=allow_raw_llm)

    files: dict[str, str] = {}
    files.update(_rel_files(paths, write_template_catalog(template_catalog, paths.skills_dir)))
    files.update(_rel_files(paths, write_repair_suggestions(repair_suggestions, paths.repair_dir)))
    files.update(_rel_files(paths, write_skill_artifacts(skill_memory, submission_policy, paths.skills_dir)))

    manifest = {
        "schema_version": 1,
        "run_id": paths.run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "allow_raw_llm": allow_raw_llm,
        "llm": llm_audit.to_dict(),
        "input_hash": stable_hash(
            {
                "community_records": community_records,
                "ledger_records": ledger_records,
                "source_manifest": source_manifest,
            }
        ),
        "summary": {
            "community_records": len(community_records),
            "ledger_records": len(ledger_records),
            "template_skeletons": len(template_catalog),
            "repair_suggestions": len(repair_suggestions),
            "skill_routes": len(skill_memory),
        },
        "source_manifest": _sanitize_source_manifest(source_manifest),
        "files": files,
        "privacy_scan": {"ok": None, "findings": []},
    }
    write_json(paths.manifest_path, manifest)
    report_files = write_review_report(
        paths.review_dir,
        run_id=paths.run_id,
        template_catalog=template_catalog,
        repair_suggestions=repair_suggestions,
        skill_memory=skill_memory,
        submission_policy=submission_policy,
        manifest=manifest,
    )
    files.update(_rel_files(paths, report_files))
    manifest["files"] = files
    write_json(paths.manifest_path, manifest)

    public_manifest: dict[str, Any] | None = None
    if public_output is not None:
        public_manifest = export_public(run_dir=paths.run_dir, public_output=public_output)
        manifest["privacy_scan"] = public_manifest["privacy_scan"]
        manifest["public_output"] = str(public_output)
        write_json(paths.manifest_path, manifest)

    return {
        "ok": True,
        "run_id": paths.run_id,
        "run_dir": str(paths.run_dir),
        "public_output": str(public_output) if public_output else "",
        "manifest": manifest,
        "public_manifest": public_manifest,
    }


def export_public(*, run_dir: Path, public_output: Path) -> dict[str, Any]:
    source_files = [
        run_dir / "skills" / "template_catalog.redacted.jsonl",
        run_dir / "skills" / "template_catalog.md",
        run_dir / "skills" / "community_skill_memory.redacted.jsonl",
        run_dir / "skills" / "submission_policy.redacted.json",
        run_dir / "repair" / "near_pass_repair_suggestions.jsonl",
        run_dir / "repair" / "near_pass_repair_playbook.md",
        run_dir / "review" / "review_report.html",
    ]
    findings = []
    for path in source_files:
        findings.extend(scan_file(path))
    if findings:
        raise PrivacyScanError(findings)

    ensure_dir(public_output)
    files: dict[str, str] = {}
    for source in source_files:
        target = public_output / source.name
        shutil.copy2(source, target)
        files[source.stem] = target.name
    public_manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": run_dir.name,
        "privacy_scan": {"ok": True, "findings": []},
        "files": files,
        "file_hashes": {name: file_hash(public_output / filename) for name, filename in files.items()},
    }
    write_json(public_output / "manifest.json", public_manifest)
    return public_manifest


def synthetic_ledger_records() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "synthetic-alpha-near-pass",
            "risk_flags": ["metric_near_pass"],
            "fitness": 0.97,
            "reason": "fitness close to threshold without hard block",
        },
        {
            "candidate_id": "synthetic-alpha-corr",
            "risk_flags": ["correlation_risk"],
            "self_corr": 0.71,
            "reason": "strong score but self correlation near limit",
        },
        {
            "candidate_id": "synthetic-alpha-turnover",
            "risk_flags": ["turnover_density_risk"],
            "turnover": 0.82,
            "reason": "unstable turnover and trade density",
        },
        {
            "candidate_id": "synthetic-alpha-unit",
            "risk_flags": ["unit_check"],
            "reason": "operator and unit support uncertain",
        },
    ]


def _rel_files(paths: RunPaths, files: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in files.items():
        try:
            out[key] = str(Path(value).relative_to(paths.run_dir)).replace("\\", "/")
        except ValueError:
            out[key] = str(value)
    return out


def _sanitize_source_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    safe = dict(manifest)
    safe.pop("files", None)
    auth = safe.get("auth")
    if isinstance(auth, dict):
        safe["auth"] = {
            "cookie_count": auth.get("cookie_count", 0),
            "authorization_present": bool(auth.get("authorization_present")),
        }
    return safe

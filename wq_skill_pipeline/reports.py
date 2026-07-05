from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .io_utils import write_text


def render_review_report(
    *,
    run_id: str,
    template_catalog: list[dict[str, Any]],
    repair_suggestions: list[dict[str, Any]],
    skill_memory: list[dict[str, Any]],
    submission_policy: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>WQ Community Skills Review - {html.escape(run_id)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; color: #202124; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #d8dce3; border-radius: 8px; padding: 12px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #d8dce3; padding: 8px; vertical-align: top; }}
    th {{ background: #f5f7fa; text-align: left; }}
    code {{ background: #f1f3f4; padding: 1px 4px; border-radius: 4px; }}
    .ok {{ color: #137333; font-weight: 700; }}
    .warn {{ color: #a05a00; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>WQ Community Skills Review</h1>
  <p>Run <code>{html.escape(run_id)}</code>. Public-safe report for template skeletons and near-pass repair routes.</p>
  <div class="grid">
    <div class="card"><strong>Templates</strong><br>{len(template_catalog)}</div>
    <div class="card"><strong>Repair Suggestions</strong><br>{len(repair_suggestions)}</div>
    <div class="card"><strong>Skill Routes</strong><br>{len(skill_memory)}</div>
    <div class="card"><strong>Privacy Scan</strong><br>{_privacy_status(manifest)}</div>
  </div>
  <h2>Template Skeletons</h2>
  {_template_table(template_catalog)}
  <h2>Near-Pass Repair Suggestions</h2>
  {_repair_table(repair_suggestions)}
  <h2>Submission Policy</h2>
  <pre>{html.escape(_compact(submission_policy))}</pre>
  <h2>Run Manifest</h2>
  <pre>{html.escape(_compact(manifest))}</pre>
</body>
</html>
"""


def write_review_report(
    output_dir: Path,
    *,
    run_id: str,
    template_catalog: list[dict[str, Any]],
    repair_suggestions: list[dict[str, Any]],
    skill_memory: list[dict[str, Any]],
    submission_policy: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, str]:
    report_path = output_dir / "review_report.html"
    write_text(
        report_path,
        render_review_report(
            run_id=run_id,
            template_catalog=template_catalog,
            repair_suggestions=repair_suggestions,
            skill_memory=skill_memory,
            submission_policy=submission_policy,
            manifest=manifest,
        ),
    )
    return {"review_report_html": str(report_path)}


def _template_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No template skeletons found.</p>"
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td><code>{html.escape(str(row.get('template_id')))}</code></td>"
            f"<td>{html.escape(', '.join(row.get('field_families', [])))}</td>"
            f"<td>{html.escape(str(row.get('operator_skeleton')))}</td>"
            f"<td>{html.escape(', '.join(row.get('risk_flags', [])))}</td>"
            "</tr>"
        )
    return (
        "<table>\n<tr><th>Template</th><th>Families</th><th>Skeleton</th><th>Risk Flags</th></tr>\n"
        + "\n".join(body)
        + "\n</table>"
    )


def _repair_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No repair suggestions found.</p>"
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('priority')))}</td>"
            f"<td>{html.escape(str(row.get('failure_bucket')))}</td>"
            f"<td>{html.escape(str(row.get('recommended_repair')))}</td>"
            f"<td>{html.escape(', '.join(row.get('community_skill_route', [])))}</td>"
            "</tr>"
        )
    return (
        "<table>\n<tr><th>Priority</th><th>Bucket</th><th>Repair</th><th>Route</th></tr>\n"
        + "\n".join(body)
        + "\n</table>"
    )


def _privacy_status(manifest: dict[str, Any]) -> str:
    scan = manifest.get("privacy_scan") if isinstance(manifest.get("privacy_scan"), dict) else {}
    if scan.get("ok"):
        return '<span class="ok">passed</span>'
    return '<span class="warn">not exported or failed</span>'


def _compact(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)

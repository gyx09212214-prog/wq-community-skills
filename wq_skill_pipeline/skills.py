from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .io_utils import write_json, write_jsonl


def build_skill_memory(
    template_catalog: list[dict[str, Any]],
    repair_suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    template_flags = Counter(flag for row in template_catalog for flag in row.get("risk_flags", []))
    repair_buckets = Counter(row.get("failure_bucket") for row in repair_suggestions)
    template_families = Counter(family for row in template_catalog for family in row.get("field_families", []))
    routes = [
        {
            "schema_version": 1,
            "memory_kind": "community_near_pass_repair_skill",
            "skill_id": "community::near_pass_repair",
            "action": "Route near-pass records to metric overlay, settings grid, or family-shift repair before fresh exploration.",
            "evidence": {
                "repair_suggestions": sum(
                    repair_buckets[bucket] for bucket in ("metric_near_pass", "correlation_similarity")
                ),
                "buckets": {
                    "metric_near_pass": repair_buckets.get("metric_near_pass", 0),
                    "correlation_similarity": repair_buckets.get("correlation_similarity", 0),
                },
            },
            "anti_patterns": ["single-window tweak for correlation failures", "submit without fresh check"],
        },
        {
            "schema_version": 1,
            "memory_kind": "community_template_transform_skill",
            "skill_id": "community::alpha_template_transform",
            "action": "Treat community templates as structural grammar only; require field/operator-family change and orthogonal overlay.",
            "evidence": {
                "template_skeletons": len(template_catalog),
                "template_risk_count": template_flags.get("private_or_public_template_risk", 0),
                "field_families": dict(sorted(template_families.items())),
            },
            "anti_patterns": ["direct forum copy", "unchanged template", "complete expression in public artifact"],
        },
        {
            "schema_version": 1,
            "memory_kind": "community_operation_attribution_skill",
            "skill_id": "community::operation_attribution",
            "action": "Attribute turnover, coverage, unit, and platform failures before mutating candidates.",
            "evidence": {
                "turnover_density": repair_buckets.get("turnover_density", 0),
                "coverage_concentration": repair_buckets.get("coverage_concentration", 0),
                "unit_platform": repair_buckets.get("unit_platform", 0),
            },
            "anti_patterns": ["mutate before diagnosing failure type", "assume operator support from forum text"],
        },
        {
            "schema_version": 1,
            "memory_kind": "community_submission_gate_skill",
            "skill_id": "community::submission_gate",
            "action": "Block direct templates, stale checks, unsupported operators, duplicate signatures, and private snippets.",
            "evidence": {
                "hard_blocks": repair_buckets.get("hard_block", 0),
                "template_risks": template_flags.get("private_or_public_template_risk", 0),
            },
            "anti_patterns": ["submit direct template", "ignore stale or pending checks"],
        },
    ]
    return routes


def build_submission_policy(
    template_catalog: list[dict[str, Any]],
    repair_suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    flags = sorted({flag for row in template_catalog for flag in row.get("risk_flags", [])})
    buckets = sorted({str(row.get("failure_bucket")) for row in repair_suggestions if row.get("failure_bucket")})
    return {
        "schema_version": 1,
        "policy_id": "community_submission_policy::redacted",
        "default_action": "human_review_required",
        "hard_block_flags": [
            "private_or_public_template_risk",
            "template_clone_risk",
            "unsupported_operator",
            "hard_block",
        ],
        "penalize_flags": [
            "correlation_risk",
            "turnover_density_risk",
            "field_family_crowding",
            "stale_precheck_risk",
            "low_coverage_risk",
        ],
        "required_before_submit_review": [
            "fresh platform check",
            "latest correlation check",
            "not a direct community template",
            "human submit boundary",
        ],
        "observed_template_flags": flags,
        "observed_repair_buckets": buckets,
        "actions": {
            "template_skeleton": "transform_before_use",
            "metric_near_pass": "repair_or_refresh_check",
            "correlation_similarity": "settings_grid_then_family_shift",
            "turnover_density": "smooth_and_density_recheck",
            "coverage_concentration": "add_broad_coverage_leg",
            "unit_platform": "legal_input_probe",
        },
    }


def write_skill_artifacts(
    skill_memory: list[dict[str, Any]],
    submission_policy: dict[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    skill_path = output_dir / "community_skill_memory.redacted.jsonl"
    policy_path = output_dir / "submission_policy.redacted.json"
    write_jsonl(skill_path, skill_memory)
    write_json(policy_path, submission_policy)
    return {"skill_memory_jsonl": str(skill_path), "submission_policy_json": str(policy_path)}

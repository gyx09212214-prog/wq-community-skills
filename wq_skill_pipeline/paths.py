from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def default_home() -> Path:
    return Path.home() / ".wq_skill_pipeline"


def default_runs_root() -> Path:
    return default_home() / "runs"


def default_state_path() -> Path:
    return default_home() / "secrets" / "wq_community_state.json"


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.run_dir / "raw"

    @property
    def normalized_dir(self) -> Path:
        return self.run_dir / "normalized"

    @property
    def triage_dir(self) -> Path:
        return self.run_dir / "triage"

    @property
    def skills_dir(self) -> Path:
        return self.run_dir / "skills"

    @property
    def repair_dir(self) -> Path:
        return self.run_dir / "repair"

    @property
    def review_dir(self) -> Path:
        return self.run_dir / "review"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"


def make_run_paths(runs_root: Path, run_id: str | None = None, prefix: str = "run") -> RunPaths:
    resolved_id = run_id or new_run_id(prefix)
    return RunPaths(run_id=resolved_id, run_dir=runs_root / resolved_id)

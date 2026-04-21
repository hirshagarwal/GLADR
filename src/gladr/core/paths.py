"""Path helpers for the GLADR project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    data_dir: Path
    raw_data_dir: Path
    notebooks_dir: Path
    outputs_dir: Path
    clean_outputs_dir: Path
    stats_outputs_dir: Path
    dashboard_outputs_dir: Path

    @classmethod
    def discover(cls) -> "ProjectPaths":
        root = Path(__file__).resolve().parents[3]
        return cls(
            root=root,
            data_dir=root / "data",
            raw_data_dir=root / "data" / "raw",
            notebooks_dir=root / "notebooks",
            outputs_dir=root / "outputs",
            clean_outputs_dir=root / "outputs" / "clean",
            stats_outputs_dir=root / "outputs" / "stats",
            dashboard_outputs_dir=root / "outputs" / "dashboard",
        )

    def ensure_runtime_dirs(self) -> None:
        for directory in (
            self.outputs_dir,
            self.clean_outputs_dir,
            self.stats_outputs_dir,
            self.dashboard_outputs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

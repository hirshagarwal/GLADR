"""Build the dashboard shell."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from gladr.core.paths import ProjectPaths


def build_dashboard(paths: ProjectPaths | None = None) -> Path:
    paths = paths or ProjectPaths.discover()
    paths.ensure_runtime_dirs()

    source = resources.files("gladr.dashboard.static_app").joinpath("index.html")
    destination = paths.dashboard_builds_outputs_dir / "index.html"
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination

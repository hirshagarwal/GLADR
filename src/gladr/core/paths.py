"""Path helpers for GLADR repositories and project workspaces."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECTS_DIR_NAME = "projects"
LOCAL_STATE_DIR_NAME = ".gladr"
PROJECT_REGISTRY_FILENAME = "projects.json"


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    root: Path
    project_id: str | None
    data_dir: Path
    raw_data_dir: Path
    interim_data_dir: Path
    reference_data_dir: Path
    registry_raw_dir: Path
    registry_main_sheet_dir: Path
    registry_workbooks_dir: Path
    histology_raw_dir: Path
    histology_text_reports_dir: Path
    histology_interim_dir: Path
    histology_marker_csv_dir: Path
    notebooks_dir: Path
    deliverables_dir: Path
    specs_dir: Path
    ingestion_specs_dir: Path
    outputs_dir: Path
    ingestion_outputs_dir: Path
    canonical_ingestion_outputs_dir: Path
    canonical_datasets_outputs_dir: Path
    canonical_manifests_outputs_dir: Path
    canonical_reports_outputs_dir: Path
    histology_ingestion_outputs_dir: Path
    histology_datasets_outputs_dir: Path
    histology_manifests_outputs_dir: Path
    histology_reports_outputs_dir: Path
    analysis_outputs_dir: Path
    analysis_artifacts_outputs_dir: Path
    analysis_manifests_outputs_dir: Path
    dashboard_outputs_dir: Path
    dashboard_builds_outputs_dir: Path

    @classmethod
    def discover(cls) -> "ProjectPaths":
        repo_root = discover_repo_root()
        project_root, project_id = resolve_active_project(repo_root)
        return cls.from_root(project_root, repo_root=repo_root, project_id=project_id)

    @classmethod
    def from_root(
        cls,
        root: Path,
        *,
        repo_root: Path | None = None,
        project_id: str | None = None,
    ) -> "ProjectPaths":
        root = root.resolve()
        repo_root = (repo_root or root).resolve()
        return cls(
            repo_root=repo_root,
            root=root,
            project_id=project_id,
            data_dir=root / "data",
            raw_data_dir=root / "data" / "raw",
            interim_data_dir=root / "data" / "interim",
            reference_data_dir=root / "data" / "reference",
            registry_raw_dir=root / "data" / "raw" / "registry",
            registry_main_sheet_dir=root / "data" / "raw" / "registry" / "main_sheet",
            registry_workbooks_dir=root / "data" / "raw" / "registry" / "workbooks",
            histology_raw_dir=root / "data" / "raw" / "histology",
            histology_text_reports_dir=root / "data" / "raw" / "histology" / "text_reports",
            histology_interim_dir=root / "data" / "interim" / "histology",
            histology_marker_csv_dir=root / "data" / "interim" / "histology" / "extracted_marker_csv",
            notebooks_dir=root / "notebooks",
            deliverables_dir=root / "deliverables",
            specs_dir=root / "specs",
            ingestion_specs_dir=root / "specs" / "ingestion",
            outputs_dir=root / "outputs",
            ingestion_outputs_dir=root / "outputs" / "ingestion",
            canonical_ingestion_outputs_dir=root / "outputs" / "ingestion" / "canonical",
            canonical_datasets_outputs_dir=root / "outputs" / "ingestion" / "canonical" / "datasets",
            canonical_manifests_outputs_dir=root / "outputs" / "ingestion" / "canonical" / "manifests",
            canonical_reports_outputs_dir=root / "outputs" / "ingestion" / "canonical" / "reports",
            histology_ingestion_outputs_dir=root / "outputs" / "ingestion" / "histology",
            histology_datasets_outputs_dir=root / "outputs" / "ingestion" / "histology" / "datasets",
            histology_manifests_outputs_dir=root / "outputs" / "ingestion" / "histology" / "manifests",
            histology_reports_outputs_dir=root / "outputs" / "ingestion" / "histology" / "reports",
            analysis_outputs_dir=root / "outputs" / "analysis",
            analysis_artifacts_outputs_dir=root / "outputs" / "analysis" / "artifacts",
            analysis_manifests_outputs_dir=root / "outputs" / "analysis" / "manifests",
            dashboard_outputs_dir=root / "outputs" / "dashboard",
            dashboard_builds_outputs_dir=root / "outputs" / "dashboard" / "builds",
        )

    def ensure_runtime_dirs(self) -> None:
        for directory in (
            self.histology_marker_csv_dir,
            self.ingestion_specs_dir,
            self.outputs_dir,
            self.ingestion_outputs_dir,
            self.canonical_ingestion_outputs_dir,
            self.canonical_datasets_outputs_dir,
            self.canonical_manifests_outputs_dir,
            self.canonical_reports_outputs_dir,
            self.histology_ingestion_outputs_dir,
            self.histology_datasets_outputs_dir,
            self.histology_manifests_outputs_dir,
            self.histology_reports_outputs_dir,
            self.analysis_outputs_dir,
            self.analysis_artifacts_outputs_dir,
            self.analysis_manifests_outputs_dir,
            self.dashboard_outputs_dir,
            self.dashboard_builds_outputs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def clean_outputs_dir(self) -> Path:
        """Backward-compatible alias for the canonical ingestion output root."""
        return self.canonical_ingestion_outputs_dir

    @property
    def stats_outputs_dir(self) -> Path:
        """Backward-compatible alias for the old analysis artifact directory."""
        return self.analysis_artifacts_outputs_dir

    @property
    def registry_ingestion_outputs_dir(self) -> Path:
        """Backward-compatible alias for canonical ingestion outputs."""
        return self.canonical_ingestion_outputs_dir

    @property
    def registry_datasets_outputs_dir(self) -> Path:
        """Backward-compatible alias for canonical clean datasets."""
        return self.canonical_datasets_outputs_dir

    @property
    def registry_manifests_outputs_dir(self) -> Path:
        """Backward-compatible alias for canonical ingestion manifests."""
        return self.canonical_manifests_outputs_dir

    @property
    def registry_reports_outputs_dir(self) -> Path:
        """Backward-compatible alias for canonical ingestion quality reports."""
        return self.canonical_reports_outputs_dir

    def ingestion_source_outputs_dir(self, source_id: str) -> Path:
        return self.ingestion_outputs_dir / "sources" / source_id

    def ingestion_source_datasets_dir(self, source_id: str) -> Path:
        return self.ingestion_source_outputs_dir(source_id) / "datasets"

    def ingestion_source_manifests_dir(self, source_id: str) -> Path:
        return self.ingestion_source_outputs_dir(source_id) / "manifests"

    def ingestion_source_reports_dir(self, source_id: str) -> Path:
        return self.ingestion_source_outputs_dir(source_id) / "reports"


@dataclass(frozen=True)
class ProjectContext:
    repo_root: Path
    project_root: Path
    project_id: str | None
    label: str | None
    paths: ProjectPaths

    @classmethod
    def discover(cls) -> "ProjectContext":
        repo_root = discover_repo_root()
        project_root, project_id = resolve_active_project(repo_root)
        metadata = read_project_metadata(project_root)
        return cls(
            repo_root=repo_root,
            project_root=project_root,
            project_id=project_id or _metadata_id(metadata),
            label=_metadata_label(metadata),
            paths=ProjectPaths.from_root(project_root, repo_root=repo_root, project_id=project_id),
        )

    @classmethod
    def from_project_root(
        cls,
        project_root: Path,
        *,
        repo_root: Path | None = None,
        project_id: str | None = None,
    ) -> "ProjectContext":
        resolved_repo = (repo_root or discover_repo_root()).resolve()
        resolved_project = project_root.resolve()
        metadata = read_project_metadata(resolved_project)
        resolved_project_id = project_id or _metadata_id(metadata)
        return cls(
            repo_root=resolved_repo,
            project_root=resolved_project,
            project_id=resolved_project_id,
            label=_metadata_label(metadata),
            paths=ProjectPaths.from_root(
                resolved_project,
                repo_root=resolved_repo,
                project_id=resolved_project_id,
            ),
        )


def discover_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def local_project_registry_path(repo_root: Path | None = None) -> Path:
    root = repo_root or discover_repo_root()
    return root / LOCAL_STATE_DIR_NAME / PROJECT_REGISTRY_FILENAME


def resolve_active_project(repo_root: Path | None = None) -> tuple[Path, str | None]:
    root = repo_root or discover_repo_root()
    env_project_root = os.environ.get("GLADR_PROJECT_ROOT")
    if env_project_root:
        return Path(env_project_root).expanduser().resolve(), None

    registry = read_local_project_registry(root)
    active_project = registry.get("active_project")
    projects = registry.get("projects")
    if active_project and isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict) or project.get("id") != active_project:
                continue
            path = project.get("path")
            if isinstance(path, str) and path:
                return _resolve_registry_project_path(root, path), str(active_project)

    raise FileNotFoundError(
        "No active GLADR project is configured. Pass --project-root, set "
        "GLADR_PROJECT_ROOT, or open/create a project from the UI."
    )


def read_local_project_registry(repo_root: Path | None = None) -> dict[str, Any]:
    path = local_project_registry_path(repo_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_project_metadata(project_root: Path) -> dict[str, Any]:
    try:
        payload = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def paths_from_project_args(
    *,
    project_root: str | Path | None = None,
    project_id: str | None = None,
) -> ProjectPaths:
    repo_root = discover_repo_root()
    if project_root is not None:
        return ProjectPaths.from_root(Path(project_root).expanduser(), repo_root=repo_root, project_id=project_id)

    if project_id:
        registry = read_local_project_registry(repo_root)
        for project in registry.get("projects", []):
            if isinstance(project, dict) and project.get("id") == project_id and isinstance(project.get("path"), str):
                return ProjectPaths.from_root(
                    _resolve_registry_project_path(repo_root, project["path"]),
                    repo_root=repo_root,
                    project_id=project_id,
                )
        raise FileNotFoundError(f"No GLADR project is registered with id: {project_id}")

    return ProjectPaths.discover()


def _resolve_registry_project_path(repo_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _metadata_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("id")
    return str(value) if value else None


def _metadata_label(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("label")
    return str(value) if value else None

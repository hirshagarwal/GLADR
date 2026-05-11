"""Path helpers for the GLADR project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
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
    outputs_dir: Path
    ingestion_outputs_dir: Path
    registry_ingestion_outputs_dir: Path
    registry_datasets_outputs_dir: Path
    registry_manifests_outputs_dir: Path
    registry_reports_outputs_dir: Path
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
        root = Path(__file__).resolve().parents[3]
        return cls.from_root(root)

    @classmethod
    def from_root(cls, root: Path) -> "ProjectPaths":
        return cls(
            root=root,
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
            outputs_dir=root / "outputs",
            ingestion_outputs_dir=root / "outputs" / "ingestion",
            registry_ingestion_outputs_dir=root / "outputs" / "ingestion" / "registry",
            registry_datasets_outputs_dir=root / "outputs" / "ingestion" / "registry" / "datasets",
            registry_manifests_outputs_dir=root / "outputs" / "ingestion" / "registry" / "manifests",
            registry_reports_outputs_dir=root / "outputs" / "ingestion" / "registry" / "reports",
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
            self.outputs_dir,
            self.ingestion_outputs_dir,
            self.registry_ingestion_outputs_dir,
            self.registry_datasets_outputs_dir,
            self.registry_manifests_outputs_dir,
            self.registry_reports_outputs_dir,
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
        """Backward-compatible alias for the old registry ingestion output root."""
        return self.registry_ingestion_outputs_dir

    @property
    def stats_outputs_dir(self) -> Path:
        """Backward-compatible alias for the old analysis artifact directory."""
        return self.analysis_artifacts_outputs_dir

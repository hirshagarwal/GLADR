"""Helpers for loading dashboard manifest inputs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from gladr.core.latest_pointer import read_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import DEFAULT_TIMEZONE

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.13 includes zoneinfo.
    ZoneInfo = None  # type: ignore[assignment]


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_dashboard_payload(paths: ProjectPaths | None = None) -> dict[str, Any]:
    """Build a dashboard payload by scanning runtime outputs.

    The dashboard calls this at request time, so newly generated ingestion and
    analysis artifacts appear without rebuilding the HTML shell.
    """

    project_paths = paths or ProjectPaths.discover()
    project_paths.ensure_runtime_dirs()

    latest_clean = read_latest_pointer(project_paths.clean_outputs_dir / "latest.json")
    latest_stats = read_latest_pointer(project_paths.stats_outputs_dir / "latest.json")
    ingestion_runs = discover_ingestion_runs(project_paths, latest_clean)
    analyses = discover_analysis_artifacts(project_paths, latest_stats)

    return {
        "generated_at": _now_iso(),
        "latest": {
            "clean": latest_clean,
            "stats": latest_stats,
        },
        "summary": {
            "ingestion_runs": len(ingestion_runs),
            "analysis_artifacts": len(analyses),
            "visualizations": sum(1 for analysis in analyses if analysis.get("visualization")),
        },
        "ingestion_runs": ingestion_runs,
        "analyses": analyses,
        "pipeline": build_pipeline_summary(ingestion_runs, analyses),
    }


def discover_ingestion_runs(
    paths: ProjectPaths,
    latest_clean: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    latest = latest_clean or {}
    latest_manifest = latest.get("run_manifest")
    runs: list[dict[str, Any]] = []

    for manifest_path in sorted(paths.clean_outputs_dir.glob("run_manifest_*.json")):
        manifest = _load_json_object(manifest_path)
        if not manifest:
            continue

        run_id = str(manifest.get("run_id") or _run_id_from_filename(manifest_path, "run_manifest_"))
        report_filename = f"ingestion_report_{run_id}.json"
        clean_filename = f"clean_dataset_{run_id}.json"

        runs.append(
            {
                "run_id": run_id,
                "run_datetime": manifest.get("run_datetime"),
                "pipeline_version": manifest.get("pipeline_version"),
                "canonical_schema_version": manifest.get("canonical_schema_version"),
                "total_rows": manifest.get("total_rows"),
                "sources": manifest.get("sources", []),
                "notes": manifest.get("notes", ""),
                "manifest_filename": manifest_path.name,
                "clean_dataset_filename": clean_filename if (paths.clean_outputs_dir / clean_filename).exists() else None,
                "ingestion_report_filename": report_filename if (paths.clean_outputs_dir / report_filename).exists() else None,
                "is_latest": manifest_path.name == latest_manifest,
            }
        )

    return sorted(runs, key=lambda run: str(run.get("run_datetime") or run.get("run_id") or ""), reverse=True)


def discover_analysis_artifacts(
    paths: ProjectPaths,
    latest_stats: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    latest_by_filename = {str(filename): script_id for script_id, filename in (latest_stats or {}).items()}
    artifacts: list[dict[str, Any]] = []

    for artifact_path in sorted(paths.stats_outputs_dir.glob("*.json")):
        if artifact_path.name == "latest.json":
            continue

        artifact = _load_json_object(artifact_path)
        if not artifact:
            continue

        script_id = str(artifact.get("script_id") or _script_id_from_filename(artifact_path))
        visualization = artifact.get("visualization")
        artifacts.append(
            {
                "filename": artifact_path.name,
                "script_id": script_id,
                "run_id": artifact.get("run_id"),
                "manifest_run_id": artifact.get("manifest_run_id"),
                "run_datetime": artifact.get("run_datetime"),
                "title": artifact.get("title") or script_id.replace("_", " ").title(),
                "description": artifact.get("description", ""),
                "category": artifact.get("category", "Uncategorized"),
                "priority": artifact.get("priority", 99),
                "metadata": artifact.get("metadata", {}),
                "visualization": visualization,
                "data": artifact.get("data", {}),
                "is_latest": artifact_path.name in latest_by_filename,
                "latest_script_id": latest_by_filename.get(artifact_path.name),
                "visualization_type": _visualization_type(visualization),
            }
        )

    artifacts.sort(key=lambda artifact: str(artifact.get("title") or ""))
    artifacts.sort(key=lambda artifact: str(artifact.get("run_datetime") or artifact.get("run_id") or ""), reverse=True)
    artifacts.sort(key=lambda artifact: int(artifact.get("priority") or 99))
    artifacts.sort(key=lambda artifact: 0 if artifact.get("is_latest") else 1)
    return artifacts


def build_pipeline_summary(
    ingestion_runs: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    analyses_by_manifest: dict[str, list[dict[str, Any]]] = {}
    for analysis in analyses:
        manifest_run_id = analysis.get("manifest_run_id")
        if manifest_run_id is None:
            continue
        analyses_by_manifest.setdefault(str(manifest_run_id), []).append(analysis)

    summary: list[dict[str, Any]] = []
    known_manifest_ids = {str(run.get("run_id")) for run in ingestion_runs if run.get("run_id") is not None}

    for run in ingestion_runs:
        run_id = str(run.get("run_id"))
        run_analyses = analyses_by_manifest.get(run_id, [])
        summary.append(
            {
                "manifest_run_id": run_id,
                "ingestion": _pipeline_ingestion_node(run),
                "stats_runs": [_pipeline_stats_node(analysis) for analysis in run_analyses],
                "visualizations": [_pipeline_visualization_node(analysis) for analysis in run_analyses],
            }
        )

    orphaned = [analysis for analysis in analyses if str(analysis.get("manifest_run_id")) not in known_manifest_ids]
    if orphaned:
        summary.append(
            {
                "manifest_run_id": None,
                "ingestion": None,
                "stats_runs": [_pipeline_stats_node(analysis) for analysis in orphaned],
                "visualizations": [_pipeline_visualization_node(analysis) for analysis in orphaned],
            }
        )

    return summary


def _pipeline_ingestion_node(run: dict[str, Any]) -> dict[str, Any]:
    sources = run.get("sources")
    source_count = len(sources) if isinstance(sources, list) else 0
    return {
        "id": run.get("run_id"),
        "label": f"Ingestion {run.get('run_id')}",
        "run_datetime": run.get("run_datetime"),
        "total_rows": run.get("total_rows"),
        "source_count": source_count,
        "is_latest": run.get("is_latest", False),
    }


def _pipeline_stats_node(analysis: dict[str, Any]) -> dict[str, Any]:
    metadata = analysis.get("metadata") if isinstance(analysis.get("metadata"), dict) else {}
    return {
        "id": analysis.get("filename"),
        "label": analysis.get("title"),
        "script_id": analysis.get("script_id"),
        "run_id": analysis.get("run_id"),
        "run_datetime": analysis.get("run_datetime"),
        "n": metadata.get("n"),
        "is_latest": analysis.get("is_latest", False),
    }


def _pipeline_visualization_node(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": analysis.get("filename"),
        "label": analysis.get("title"),
        "type": analysis.get("visualization_type"),
        "script_id": analysis.get("script_id"),
        "run_datetime": analysis.get("run_datetime"),
        "is_latest": analysis.get("is_latest", False),
    }


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_id_from_filename(path: Path, prefix: str) -> str:
    stem = path.stem
    return stem.removeprefix(prefix)


def _script_id_from_filename(path: Path) -> str:
    stem_parts = path.stem.split("_")
    if len(stem_parts) >= 3 and stem_parts[-2].isdigit() and stem_parts[-1].isdigit():
        return "_".join(stem_parts[:-2])
    return path.stem


def _visualization_type(visualization: object) -> str | None:
    if not isinstance(visualization, dict):
        return None
    visualization_type = visualization.get("type")
    return str(visualization_type) if visualization_type is not None else None


def _now_iso() -> str:
    if ZoneInfo is None:
        return datetime.now().isoformat(timespec="seconds")
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")

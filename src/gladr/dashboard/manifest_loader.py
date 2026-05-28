"""Helpers for loading dashboard manifest inputs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from gladr.analysis.profiling import build_dataset_profile
from gladr.analysis.templates import list_analysis_templates
from gladr.core.latest_pointer import read_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import DEFAULT_TIMEZONE
from gladr.ingestion.workbench import build_ingestion_workbench_payload

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

    latest_clean = read_latest_pointer(project_paths.canonical_ingestion_outputs_dir / "latest.json")
    latest_stats = read_latest_pointer(project_paths.analysis_outputs_dir / "latest.json")
    ingestion_runs = discover_ingestion_runs(project_paths, latest_clean)
    analyses = discover_analysis_artifacts(project_paths, latest_stats)
    _attach_cohort_traces(analyses, ingestion_runs)

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
        "dataset_profile": build_dataset_profile(project_paths),
        "analysis_templates": list_analysis_templates(),
        "ingestion_workbench": build_ingestion_workbench_payload(project_paths),
        "ingestion_runs": ingestion_runs,
        "analyses": analyses,
        "pipeline": build_pipeline_summary(ingestion_runs, analyses),
        "stage_summaries": build_stage_summaries(ingestion_runs, analyses),
    }


def discover_ingestion_runs(
    paths: ProjectPaths,
    latest_clean: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    latest = latest_clean or {}
    latest_manifest = latest.get("manifest") or latest.get("run_manifest")
    runs: list[dict[str, Any]] = []

    for manifest_path in sorted(paths.canonical_manifests_outputs_dir.glob("manifest_*.json")):
        manifest = _load_json_object(manifest_path)
        if not manifest:
            continue

        run_id = str(manifest.get("run_id") or _run_id_from_filename(manifest_path, "manifest_"))
        report_filename = f"quality_report_{run_id}.json"
        report_path = paths.canonical_reports_outputs_dir / report_filename
        clean_filename = f"clean_dataset_{run_id}.json"
        report_summary = _summarize_ingestion_report(report_path)
        manifest_pointer = manifest_path.relative_to(paths.canonical_ingestion_outputs_dir).as_posix()

        runs.append(
            {
                "run_id": run_id,
                "run_datetime": manifest.get("run_datetime"),
                "pipeline_version": manifest.get("pipeline_version"),
                "canonical_schema_version": manifest.get("canonical_schema_version"),
                "total_rows": manifest.get("total_rows"),
                "sources": manifest.get("sources", []),
                "summary": manifest.get("summary", {}),
                "steps": manifest.get("steps", []),
                "filter_steps": _filter_steps_from_specs(manifest),
                "notes": manifest.get("notes", ""),
                "manifest_filename": manifest_pointer,
                "clean_dataset_filename": f"datasets/{clean_filename}"
                if (paths.canonical_datasets_outputs_dir / clean_filename).exists()
                else None,
                "ingestion_report_filename": f"reports/{report_filename}" if report_path.exists() else None,
                "flagged_records": report_summary["flagged_records"],
                "quality_flags": report_summary["quality_flags"],
                "is_latest": manifest_pointer == latest_manifest,
            }
        )

    return sorted(runs, key=lambda run: str(run.get("run_datetime") or run.get("run_id") or ""), reverse=True)


def discover_analysis_artifacts(
    paths: ProjectPaths,
    latest_stats: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    latest_by_filename = {Path(str(filename)).name: script_id for script_id, filename in (latest_stats or {}).items()}
    artifacts: list[dict[str, Any]] = []

    for artifact_path in sorted(paths.analysis_artifacts_outputs_dir.glob("*.json")):
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
                "cohort_display": _cohort_display_policy(artifact),
                "cohort": artifact.get("cohort", {}),
                "visualization": visualization,
                "data": artifact.get("data", {}),
                "is_latest": artifact_path.name in latest_by_filename,
                "latest_script_id": latest_by_filename.get(artifact_path.name),
                "visualization_type": _visualization_type(visualization),
            }
        )

    artifacts.sort(key=lambda artifact: str(artifact.get("title") or ""))
    artifacts.sort(key=lambda artifact: int(artifact.get("priority") or 99))
    artifacts.sort(key=lambda artifact: 0 if artifact.get("is_latest") else 1)
    artifacts.sort(key=lambda artifact: str(artifact.get("run_datetime") or artifact.get("run_id") or ""), reverse=True)
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


def build_stage_summaries(
    ingestion_runs: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return stage-centric data for the dashboard landing view."""

    latest_ingestion = next(
        (run for run in ingestion_runs if run.get("is_latest")),
        ingestion_runs[0] if ingestion_runs else None,
    )
    latest_analysis = _latest_analysis_run_artifacts(analyses)
    visualization_artifacts = [analysis for analysis in analyses if analysis.get("visualization")]
    latest_visualizations = _latest_analysis_run_artifacts(visualization_artifacts)

    analysis_history = _group_analysis_history(analyses, include_visualizations=False)
    visualization_history = _group_analysis_history(visualization_artifacts, include_visualizations=True)

    return [
        {
            "id": "ingestion",
            "label": "Ingestion",
            "status": "completed" if latest_ingestion else "pending",
            "current": _ingestion_stage_item(latest_ingestion),
            "history": [_ingestion_stage_item(run) for run in ingestion_runs],
        },
        {
            "id": "analysis",
            "label": "Analysis",
            "status": "completed" if latest_analysis else ("failed" if latest_ingestion else "pending"),
            "current": _analysis_stage_item("Analysis", latest_analysis),
            "history": analysis_history,
        },
        {
            "id": "visualization",
            "label": "Visualization",
            "status": "completed" if latest_visualizations else ("failed" if latest_analysis else "pending"),
            "current": _analysis_stage_item("Visualization", latest_visualizations),
            "history": visualization_history,
        },
    ]


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


def _ingestion_stage_item(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None

    sources = run.get("sources") if isinstance(run.get("sources"), list) else []
    files = [
        filename
        for filename in (
            run.get("manifest_filename"),
            run.get("clean_dataset_filename"),
            run.get("ingestion_report_filename"),
        )
        if filename
    ]
    return {
        "title": f"Ingestion run {run.get('run_id')}",
        "run_id": run.get("run_id"),
        "run_datetime": run.get("run_datetime"),
        "description": "Canonical clean dataset and run manifest generated from source adapters.",
        "metrics": [
            {"label": "Rows", "value": run.get("total_rows", "NA")},
            {"label": "Sources", "value": len(sources)},
            {"label": "Flagged records", "value": run.get("flagged_records", "NA")},
        ],
        "outputs": [
            {
                "label": source.get("file", "Source file") if isinstance(source, dict) else "Source file",
                "detail": _source_detail(source),
            }
            for source in sources
        ],
        "files": files,
        "flow": _ingestion_flow(run, sources, files),
        "is_latest": run.get("is_latest", False),
    }


def _ingestion_flow(
    run: dict[str, Any],
    sources: list[object],
    files: list[object],
) -> dict[str, list[dict[str, object]]]:
    total_raw = sum(int(source.get("rows_raw") or 0) for source in sources if isinstance(source, dict))
    total_stub = sum(int(source.get("rows_stub") or 0) for source in sources if isinstance(source, dict))
    adapters = sorted({str(source.get("adapter")) for source in sources if isinstance(source, dict) and source.get("adapter")})
    manifest_steps = run.get("steps") if isinstance(run.get("steps"), list) else []
    step_items = [_flow_step_from_manifest(step) for step in manifest_steps if isinstance(step, dict)]
    step_items = _summarize_repeated_file_steps(step_items)
    if not step_items:
        step_items = [
            {
                "label": "Read source files",
                "detail": f"{len(sources)} file{'s' if len(sources) != 1 else ''}, {total_raw} raw row{'s' if total_raw != 1 else ''}",
            },
            {
                "label": "Normalize to canonical schema",
                "detail": f"Adapter: {', '.join(adapters) if adapters else 'unknown'} | schema {run.get('canonical_schema_version', 'NA')}",
            },
            {
                "label": "Validate and flag rows",
                "detail": f"{total_stub} stub row{'s' if total_stub != 1 else ''} skipped | {run.get('flagged_records', 'NA')} flagged record{'s' if run.get('flagged_records') != 1 else ''}",
            },
            {
                "label": "Combine clean records",
                "detail": f"{run.get('total_rows', 'NA')} canonical row{'s' if run.get('total_rows') != 1 else ''}",
            },
        ]

    return {
        "inputs": [
            {
                "label": source.get("file", "Source file") if isinstance(source, dict) else "Source file",
                "detail": _source_detail(source),
            }
            for source in sources
        ],
        "steps": step_items,
        "results": [
            {
                "label": _artifact_label(str(filename)),
                "detail": str(filename),
            }
            for filename in files
        ],
    }


def _flow_step_from_manifest(step: dict[str, object]) -> dict[str, object]:
    metrics = step.get("metrics") if isinstance(step.get("metrics"), dict) else {}
    label = step.get("label") or step.get("step_id") or "Pipeline step"
    if metrics.get("operation") == "filter_rows" and metrics.get("filter_label"):
        label = f"{label} ({metrics.get('filter_label')})"
    return {
        "step_id": step.get("step_id"),
        "label": label,
        "detail": metrics.get("filter_description") or step.get("summary") or step.get("detail") or "",
        "status": step.get("status", "completed"),
        "execution_mode": step.get("execution_mode", "unknown"),
        "source_file": step.get("source_file"),
        "metrics": metrics,
    }


def _summarize_repeated_file_steps(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    ordered_items: list[dict[str, object] | tuple[str, str, str]] = []

    for step in steps:
        source_file = step.get("source_file")
        if not source_file:
            ordered_items.append(step)
            continue

        key = (
            _operation_key(str(step.get("step_id") or "")),
            str(step.get("label") or ""),
            str(step.get("execution_mode") or ""),
        )
        if key not in grouped:
            grouped[key] = []
            ordered_items.append(key)
        grouped[key].append(step)

    return [
        _summarize_step_group(grouped[item]) if isinstance(item, tuple) else item
        for item in ordered_items
    ]


def _operation_key(step_id: str) -> str:
    return step_id.split(":", 1)[1] if ":" in step_id else step_id


def _summarize_step_group(items: list[dict[str, object]]) -> dict[str, object]:
    first = items[0]
    source_files = [str(item.get("source_file")) for item in items if item.get("source_file")]
    details = [str(item.get("detail") or "") for item in items if item.get("detail")]
    unique_details = list(dict.fromkeys(details))

    if len(items) == 1:
        detail = f"{source_files[0]}: {details[0]}" if source_files and details else first.get("detail", "")
    elif len(unique_details) == 1:
        detail = f"Ran {len(items)}x, once per input file: {', '.join(source_files)}. {unique_details[0]}"
    else:
        per_file = "; ".join(
            f"{str(item.get('source_file'))}: {str(item.get('detail'))}"
            for item in items
            if item.get("source_file") and item.get("detail")
        )
        detail = f"Ran {len(items)}x, once per input file. {per_file}"

    return {
        "step_id": _operation_key(str(first.get("step_id") or "")),
        "label": first.get("label"),
        "detail": detail,
        "status": first.get("status", "completed"),
        "execution_mode": first.get("execution_mode", "unknown"),
        "source_files": source_files,
        "run_count": len(items),
    }


def _filter_steps_from_specs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    specs = manifest.get("specs") if isinstance(manifest.get("specs"), list) else []
    filters: list[dict[str, Any]] = []
    for spec_snapshot in specs:
        if not isinstance(spec_snapshot, dict):
            continue
        spec = spec_snapshot.get("spec") if isinstance(spec_snapshot.get("spec"), dict) else {}
        source_file = spec_snapshot.get("source_file")
        for position, step in enumerate(spec.get("steps", []), start=1):
            if not isinstance(step, dict) or step.get("operation") != "filter_rows":
                continue
            params = step.get("params") if isinstance(step.get("params"), dict) else {}
            filters.append(
                {
                    "step_id": str(step.get("id") or f"{position}:filter_rows"),
                    "label": step.get("label") or "Filter Rows",
                    "source_file": source_file,
                    "params": params,
                    "filter_label": _filter_label(params),
                    "filter_description": _filter_description(params),
                    "filter_conditions": _filter_rule_summaries(params),
                }
            )
    return filters


def _artifact_label(filename: str) -> str:
    if "/datasets/" in f"/{filename}" or filename.startswith("datasets/"):
        return "Clean dataset"
    if "/manifests/" in f"/{filename}" or filename.startswith("manifests/"):
        return "Run manifest"
    if "/reports/" in f"/{filename}" or filename.startswith("reports/"):
        return "Quality report"
    return "Runtime artifact"


def _analysis_stage_item(label: str, artifacts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not artifacts:
        return None

    run_ids = sorted({str(artifact.get("run_id")) for artifact in artifacts if artifact.get("run_id")})
    scripts = sorted({str(artifact.get("script_id")) for artifact in artifacts if artifact.get("script_id")})
    latest_datetime = max((str(artifact.get("run_datetime") or "") for artifact in artifacts), default="")
    return {
        "title": f"{label} outputs",
        "run_id": ", ".join(run_ids) if run_ids else None,
        "run_datetime": latest_datetime or None,
        "description": f"{len(artifacts)} artifact{'s' if len(artifacts) != 1 else ''} available for the latest {label.lower()} stage.",
        "metrics": [
            {"label": "Artifacts", "value": len(artifacts)},
            {"label": "Scripts", "value": len(scripts)},
        ],
        "outputs": [
            {
                "label": artifact.get("title") or artifact.get("script_id") or artifact.get("filename"),
                "detail": _analysis_detail(artifact),
            }
            for artifact in artifacts
        ],
        "files": [artifact.get("filename") for artifact in artifacts if artifact.get("filename")],
        "is_latest": any(artifact.get("is_latest") for artifact in artifacts),
    }


def _group_analysis_history(artifacts: list[dict[str, Any]], include_visualizations: bool) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        run_id = str(artifact.get("run_id") or artifact.get("run_datetime") or artifact.get("filename"))
        grouped.setdefault(run_id, []).append(artifact)

    history = [
        _analysis_stage_item("Visualization" if include_visualizations else "Analysis", items)
        for items in grouped.values()
    ]
    return sorted(
        [item for item in history if item is not None],
        key=lambda item: str(item.get("run_datetime") or item.get("run_id") or ""),
        reverse=True,
    )


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
        "cohort_display": analysis.get("cohort_display"),
        "is_latest": analysis.get("is_latest", False),
    }


def _latest_analysis_run_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not artifacts:
        return []
    latest_run_id = max(
        (str(artifact.get("run_id") or "") for artifact in artifacts),
        key=lambda run_id: max(
            str(item.get("run_datetime") or item.get("run_id") or "")
            for item in artifacts
            if str(item.get("run_id") or "") == run_id
        ),
    )
    return [artifact for artifact in artifacts if str(artifact.get("run_id") or "") == latest_run_id]


def _cohort_display_policy(artifact: dict[str, Any]) -> str:
    explicit = artifact.get("cohort_display")
    if explicit:
        return str(explicit)
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    template_id = str(metadata.get("template_id") or artifact.get("script_id") or "")
    template_policies = {
        str(template["template_id"]): str(template.get("cohort_display") or "none")
        for template in list_analysis_templates()
    }
    return template_policies.get(template_id, "none")


def _attach_cohort_traces(analyses: list[dict[str, Any]], ingestion_runs: list[dict[str, Any]]) -> None:
    ingestion_by_run = {str(run.get("run_id")): run for run in ingestion_runs if run.get("run_id")}
    for analysis in analyses:
        if analysis.get("cohort_display") == "none":
            analysis["cohort_trace"] = None
            continue
        ingestion = ingestion_by_run.get(str(analysis.get("manifest_run_id") or ""))
        analysis["cohort_trace"] = _cohort_trace(analysis, ingestion)


def _cohort_trace(analysis: dict[str, Any], ingestion_run: dict[str, Any] | None) -> dict[str, Any] | None:
    metadata = analysis.get("metadata") if isinstance(analysis.get("metadata"), dict) else {}
    cohort = analysis.get("cohort") if isinstance(analysis.get("cohort"), dict) else {}
    included_rows = _optional_int(cohort.get("included_rows")) or _optional_int(metadata.get("n"))
    if included_rows is None:
        return None

    ingestion = _ingestion_cohort_trace(ingestion_run)
    clean_rows = _optional_int(ingestion.get("clean_rows")) if ingestion else None
    input_rows = _optional_int(cohort.get("input_rows")) or clean_rows
    excluded_rows = _optional_int(cohort.get("excluded_rows"))
    if excluded_rows is None and input_rows is not None:
        excluded_rows = max(input_rows - included_rows, 0)

    rules = cohort.get("rules") if isinstance(cohort.get("rules"), list) else []
    if not rules and excluded_rows is not None:
        rules = [
            {
                "rule": "analysis_exclusion",
                "count": excluded_rows,
                "description": metadata.get("exclusions") or "Rows were excluded by the analysis cohort rule.",
            }
        ]

    return {
        "display": analysis.get("cohort_display"),
        "ingestion": ingestion,
        "analysis": {
            "input_rows": input_rows,
            "included_rows": included_rows,
            "excluded_rows": excluded_rows,
            "basis": cohort.get("basis"),
            "required_fields": cohort.get("required_fields") if isinstance(cohort.get("required_fields"), list) else [],
            "rules": rules,
        },
    }


def _ingestion_cohort_trace(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    sources = run.get("sources") if isinstance(run.get("sources"), list) else []
    raw_rows = sum(int(source.get("rows_raw") or 0) for source in sources if isinstance(source, dict))
    stub_rows = sum(int(source.get("rows_stub") or 0) for source in sources if isinstance(source, dict))
    clean_rows = _optional_int(run.get("total_rows"))
    rules = _ingestion_filter_rules(run)
    if stub_rows and not any(rule.get("rule") == "sparse_rows" for rule in rules):
        rules.insert(
            0,
            {
                "rule": "sparse_rows",
                "label": "Sparse row filter",
                "count": stub_rows,
                "description": "Rows with no patient identifier or too few populated fields were removed.",
            },
        )
    return {
        "run_id": run.get("run_id"),
        "raw_rows": raw_rows if raw_rows else None,
        "stub_rows": stub_rows,
        "clean_rows": clean_rows,
        "rules": rules,
    }


def _ingestion_filter_rules(run: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    steps = run.get("steps") if isinstance(run.get("steps"), list) else []
    filter_specs = run.get("filter_steps") if isinstance(run.get("filter_steps"), list) else []
    filter_index = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        metrics = step.get("metrics") if isinstance(step.get("metrics"), dict) else {}
        if metrics.get("operation") != "filter_rows":
            continue
        spec_filter = filter_specs[filter_index] if filter_index < len(filter_specs) and isinstance(filter_specs[filter_index], dict) else {}
        filter_index += 1
        count = _optional_int(metrics.get("filtered_rows"))
        if not count:
            continue
        filter_label = metrics.get("filter_label") or spec_filter.get("filter_label")
        label = str(step.get("label") or spec_filter.get("label") or "Filter rows")
        display_label = f"{label} ({filter_label})" if filter_label else label
        description = (
            metrics.get("filter_description")
            or spec_filter.get("filter_description")
            or step.get("summary")
            or ""
        )
        rules.append(
            {
                "rule": "sparse_rows" if "sparse" in label.lower() else "filter_rows",
                "label": display_label,
                "count": count,
                "remaining_rows": _optional_int(metrics.get("remaining_rows")),
                "description": description,
                "conditions": metrics.get("filter_conditions") or spec_filter.get("filter_conditions") or [],
            }
        )
    return rules


def _filter_label(params: dict[str, Any]) -> str:
    if params.get("minimum_populated_fields") not in (None, ""):
        return "sparse rows"
    conditions = params.get("conditions")
    if isinstance(conditions, list):
        fields = [
            str(condition.get("field"))
            for condition in conditions
            if isinstance(condition, dict) and condition.get("field")
        ]
        if fields:
            return ", ".join(dict.fromkeys(fields))
    required_field = params.get("required_field")
    if required_field:
        return str(required_field)
    return ""


def _filter_description(params: dict[str, Any]) -> str:
    pieces = _filter_condition_summaries(params)
    minimum = params.get("minimum_populated_fields")
    if minimum not in (None, ""):
        pieces.append(f"fewer than {minimum} populated field(s)")
    action = str(params.get("action") or "keep")
    match = str(params.get("match") or "all")
    if not pieces:
        return f"{action.title()} rows matching this filter."
    return f"{action.title()} rows where {match} of: {'; '.join(pieces)}."


def _filter_condition_summaries(params: dict[str, Any]) -> list[str]:
    conditions = params.get("conditions")
    if not isinstance(conditions, list):
        return []
    return [
        _filter_condition_summary(condition)
        for condition in conditions
        if isinstance(condition, dict)
    ]


def _filter_rule_summaries(params: dict[str, Any]) -> list[str]:
    summaries = _filter_condition_summaries(params)
    minimum = params.get("minimum_populated_fields")
    if minimum not in (None, ""):
        summaries.append(f"fewer than {minimum} populated field(s)")
    return summaries


def _filter_condition_summary(condition: dict[str, Any]) -> str:
    field = str(condition.get("field") or "field")
    operator = str(condition.get("operator") or "equals")
    value = condition.get("value")
    labels = {
        "is_missing": "is missing",
        "is_not_missing": "is present",
        "equals": f"equals {value}",
        "not_equals": f"does not equal {value}",
        "contains": f"contains {value}",
        "not_contains": f"does not contain {value}",
        "gt": f"> {value}",
        "gte": f">= {value}",
        "lt": f"< {value}",
        "lte": f"<= {value}",
        "in": f"in {value}",
        "not_in": f"not in {value}",
    }
    return f"{field} {labels.get(operator, operator)}"


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _summarize_ingestion_report(path: Path) -> dict[str, int]:
    payload = _load_json_array(path)
    flagged_records = 0
    quality_flags = 0
    for row in payload:
        if not isinstance(row, dict):
            continue
        flags = row.get("flags")
        if isinstance(flags, list) and flags:
            flagged_records += 1
            quality_flags += len(flags)
    return {"flagged_records": flagged_records, "quality_flags": quality_flags}


def _load_json_array(path: Path) -> list[Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _source_detail(source: object) -> str:
    if not isinstance(source, dict):
        return ""
    rows_ingested = source.get("rows_ingested")
    rows_raw = source.get("rows_raw")
    adapter = source.get("adapter")
    pieces = []
    if rows_ingested is not None:
        pieces.append(f"{rows_ingested} ingested")
    if rows_raw is not None:
        pieces.append(f"{rows_raw} raw")
    if adapter:
        pieces.append(str(adapter))
    return " | ".join(pieces)


def _analysis_detail(artifact: dict[str, Any]) -> str:
    detail = [str(value) for value in (artifact.get("category"), artifact.get("visualization_type")) if value]
    metadata = artifact.get("metadata")
    if isinstance(metadata, dict) and metadata.get("n") is not None:
        detail.append(f"n={metadata.get('n')}")
    if artifact.get("run_datetime"):
        detail.append(str(artifact.get("run_datetime")))
    return " | ".join(detail)


def _now_iso() -> str:
    if ZoneInfo is None:
        return datetime.now().isoformat(timespec="seconds")
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")

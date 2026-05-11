"""Runner for ingestion adapters."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gladr.contracts import load_contract
from gladr.core.discovery import filter_by_ids, instantiate_discovered
from gladr.core.latest_pointer import write_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import RunContext
from gladr.ingestion.adapters.base_adapter import BaseAdapter, IngestionStep


PIPELINE_VERSION = "0.1.0"


def run_ingestion(adapter_id: str | None = None, source_file: str | None = None) -> dict[str, Path]:
    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()
    run_context = RunContext.now()

    adapters = instantiate_discovered("gladr.ingestion.adapters", BaseAdapter)
    if adapter_id:
        adapters = filter_by_ids(adapters, {adapter_id}, "adapter_id")
    if not adapters:
        raise ValueError("No ingestion adapters selected")

    collected_frames: list[pd.DataFrame] = []
    source_summaries: list[dict[str, object]] = []
    ingestion_report: list[dict[str, object]] = []
    adapter_steps: list[dict[str, object]] = []

    for adapter in adapters:
        matched_files = [Path(source_file)] if source_file else adapter.match_files(paths.root)
        if not matched_files:
            continue

        for matched_file in matched_files:
            raw_df = adapter.load_raw(matched_file)
            result = adapter.transform(raw_df, matched_file)
            collected_frames.append(result.dataframe)
            source_summaries.append(result.source_summary)
            ingestion_report.extend(result.ingestion_report)
            adapter_steps.extend(_normalize_steps(result.steps))

    if not collected_frames:
        raise FileNotFoundError("No source files were found for the selected ingestion adapters")

    clean_df = pd.concat(collected_frames, ignore_index=True)
    clean_path = paths.registry_datasets_outputs_dir / f"clean_dataset_{run_context.run_id}.json"
    manifest_path = paths.registry_manifests_outputs_dir / f"manifest_{run_context.run_id}.json"
    report_path = paths.registry_reports_outputs_dir / f"quality_report_{run_context.run_id}.json"

    clean_payload = {
        "run_id": run_context.run_id,
        "run_datetime": run_context.run_datetime,
        "canonical_schema_version": load_contract("canonical_schema.json")["version"],
        "records": clean_df.to_dict(orient="records"),
    }

    manifest_summary = _build_manifest_summary(source_summaries, ingestion_report, total_rows=int(len(clean_df)))
    manifest = {
        "run_id": run_context.run_id,
        "pipeline_version": PIPELINE_VERSION,
        "run_datetime": run_context.run_datetime,
        "sources": source_summaries,
        "summary": manifest_summary,
        "steps": _build_manifest_steps(
            source_summaries,
            manifest_summary,
            canonical_schema_version=str(clean_payload["canonical_schema_version"]),
            clean_dataset_filename=clean_path.name,
            quality_report_filename=report_path.name,
            adapter_steps=adapter_steps,
        ),
        "total_rows": int(len(clean_df)),
        "canonical_schema_version": clean_payload["canonical_schema_version"],
        "notes": ""
    }

    _write_json(clean_path, clean_payload)
    _write_json(manifest_path, manifest)
    _write_json(report_path, ingestion_report)
    write_latest_pointer(
        paths.registry_ingestion_outputs_dir / "latest.json",
        {
            "clean_dataset": clean_path.relative_to(paths.registry_ingestion_outputs_dir).as_posix(),
            "manifest": manifest_path.relative_to(paths.registry_ingestion_outputs_dir).as_posix(),
            "quality_report": report_path.relative_to(paths.registry_ingestion_outputs_dir).as_posix(),
        },
    )

    return {
        "clean_dataset": clean_path,
        "manifest": manifest_path,
        "quality_report": report_path,
    }


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _normalize_steps(steps: list[IngestionStep | dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for step in steps:
        if isinstance(step, IngestionStep):
            normalized.append(step.to_manifest())
        elif isinstance(step, dict):
            normalized.append(step)
    return normalized


def _build_manifest_summary(
    source_summaries: list[dict[str, object]],
    ingestion_report: list[dict[str, object]],
    *,
    total_rows: int,
) -> dict[str, object]:
    raw_rows = sum(int(source.get("rows_raw") or 0) for source in source_summaries)
    stub_rows = sum(int(source.get("rows_stub") or 0) for source in source_summaries)
    flagged_records = 0
    quality_flags = 0
    for row in ingestion_report:
        flags = row.get("flags")
        if isinstance(flags, list) and flags:
            flagged_records += 1
            quality_flags += len(flags)

    return {
        "source_files": len(source_summaries),
        "raw_rows": raw_rows,
        "stub_rows": stub_rows,
        "ingested_rows": total_rows,
        "flagged_records": flagged_records,
        "quality_flags": quality_flags,
        "adapters": sorted({str(source.get("adapter")) for source in source_summaries if source.get("adapter")}),
    }


def _build_manifest_steps(
    source_summaries: list[dict[str, object]],
    summary: dict[str, object],
    *,
    canonical_schema_version: str,
    clean_dataset_filename: str,
    quality_report_filename: str,
    adapter_steps: list[dict[str, object]],
) -> list[dict[str, object]]:
    input_files = [str(source.get("file")) for source in source_summaries if source.get("file")]
    adapter_list = ", ".join(str(adapter) for adapter in summary.get("adapters", [])) or "unknown"
    read_step = IngestionStep(
        step_id="read_sources",
        label="Read source files",
        summary=f"{summary['source_files']} file(s), {summary['raw_rows']} raw row(s)",
        execution_mode="static_code",
        inputs=input_files,
        outputs=["raw dataframes"],
        metrics={
            "source_files": summary["source_files"],
            "raw_rows": summary["raw_rows"],
        },
    )
    normalize_step = IngestionStep(
        step_id="normalize",
        label="Normalize to canonical schema",
        summary=f"Adapter: {adapter_list} | schema {canonical_schema_version}",
        execution_mode="static_code",
        inputs=["raw dataframes"],
        outputs=["canonical records"],
        metrics={"canonical_schema_version": canonical_schema_version},
    )
    final_steps = [
        IngestionStep(
            step_id="validate_quality",
            label="Validate and flag rows",
            summary=f"{summary['stub_rows']} stub row(s) skipped | {summary['flagged_records']} flagged record(s)",
            execution_mode="static_code",
            inputs=["canonical records"],
            outputs=[quality_report_filename],
            metrics={
                "stub_rows": summary["stub_rows"],
                "flagged_records": summary["flagged_records"],
                "quality_flags": summary["quality_flags"],
            },
        ),
        IngestionStep(
            step_id="write_outputs",
            label="Write result files",
            summary=f"{summary['ingested_rows']} canonical row(s)",
            execution_mode="static_code",
            inputs=["canonical records", quality_report_filename],
            outputs=[clean_dataset_filename, quality_report_filename],
            metrics={"ingested_rows": summary["ingested_rows"]},
        ),
    ]
    return [read_step.to_manifest(), normalize_step.to_manifest(), *adapter_steps] + [
        step.to_manifest() for step in final_steps
    ]

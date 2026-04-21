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
from gladr.ingest.adapters.base_adapter import BaseAdapter


PIPELINE_VERSION = "0.1.0"


def run_ingestion(adapter_id: str | None = None, source_file: str | None = None) -> dict[str, Path]:
    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()
    run_context = RunContext.now()

    adapters = instantiate_discovered("gladr.ingest.adapters", BaseAdapter)
    if adapter_id:
        adapters = filter_by_ids(adapters, {adapter_id}, "adapter_id")
    if not adapters:
        raise ValueError("No ingestion adapters selected")

    collected_frames: list[pd.DataFrame] = []
    source_summaries: list[dict[str, object]] = []
    ingestion_report: list[dict[str, object]] = []

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

    if not collected_frames:
        raise FileNotFoundError("No source files were found for the selected ingestion adapters")

    clean_df = pd.concat(collected_frames, ignore_index=True)
    clean_path = paths.clean_outputs_dir / f"clean_dataset_{run_context.run_id}.json"
    manifest_path = paths.clean_outputs_dir / f"run_manifest_{run_context.run_id}.json"
    report_path = paths.clean_outputs_dir / f"ingestion_report_{run_context.run_id}.json"

    clean_payload = {
        "run_id": run_context.run_id,
        "run_datetime": run_context.run_datetime,
        "canonical_schema_version": load_contract("canonical_schema.json")["version"],
        "records": clean_df.to_dict(orient="records"),
    }

    manifest = {
        "run_id": run_context.run_id,
        "pipeline_version": PIPELINE_VERSION,
        "run_datetime": run_context.run_datetime,
        "sources": source_summaries,
        "total_rows": int(len(clean_df)),
        "canonical_schema_version": clean_payload["canonical_schema_version"],
        "notes": ""
    }

    _write_json(clean_path, clean_payload)
    _write_json(manifest_path, manifest)
    _write_json(report_path, ingestion_report)
    write_latest_pointer(
        paths.clean_outputs_dir / "latest.json",
        {
            "clean_dataset": clean_path.name,
            "run_manifest": manifest_path.name,
            "ingestion_report": report_path.name
        },
    )

    return {
        "clean_dataset": clean_path,
        "run_manifest": manifest_path,
        "ingestion_report": report_path,
    }


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

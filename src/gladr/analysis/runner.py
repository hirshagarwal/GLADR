"""Runner for analysis scripts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.core.discovery import filter_by_ids, instantiate_discovered
from gladr.core.latest_pointer import read_latest_pointer, write_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import RunContext


def run_analysis(script_ids: list[str] | None = None) -> dict[str, Path]:
    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()

    latest_clean = read_latest_pointer(paths.clean_outputs_dir / "latest.json")
    clean_dataset = latest_clean.get("clean_dataset")
    manifest_filename = latest_clean.get("run_manifest")
    if not clean_dataset or not manifest_filename:
        raise FileNotFoundError("No clean dataset latest pointer found. Run ingestion first.")

    clean_path = paths.clean_outputs_dir / clean_dataset
    manifest_path = paths.clean_outputs_dir / manifest_filename

    with clean_path.open("r", encoding="utf-8") as handle:
        clean_payload = json.load(handle)

    dataframe = pd.DataFrame(clean_payload["records"])
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    run_context = RunContext.now()
    scripts = instantiate_discovered("gladr.analysis.scripts", BaseAnalysisScript)
    if script_ids:
        scripts = filter_by_ids(scripts, set(script_ids), "script_id")
    if not scripts:
        raise ValueError("No analysis scripts selected")

    latest_stats = read_latest_pointer(paths.stats_outputs_dir / "latest.json")
    written: dict[str, Path] = {}

    for script in scripts:
        output = script.build(dataframe, run_context, manifest["run_id"])
        output_path = paths.stats_outputs_dir / f"{script.script_id}_{run_context.run_id}.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
            handle.write("\n")
        latest_stats[script.script_id] = output_path.name
        written[script.script_id] = output_path

    write_latest_pointer(paths.stats_outputs_dir / "latest.json", latest_stats)
    return written

"""Runner for analysis scripts."""

from __future__ import annotations

import json
from pathlib import Path

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.analysis.profiling import load_latest_clean_dataframe
from gladr.analysis.templates import run_analysis_template
from gladr.core.discovery import filter_by_ids, instantiate_discovered
from gladr.core.latest_pointer import read_latest_pointer, write_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import RunContext


def run_analysis(script_ids: list[str] | None = None) -> dict[str, Path]:
    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()

    dataframe, manifest = load_latest_clean_dataframe(paths)

    run_context = RunContext.now()
    scripts = instantiate_discovered("gladr.analysis.scripts", BaseAnalysisScript)
    if script_ids:
        scripts = filter_by_ids(scripts, set(script_ids), "script_id")
    if not scripts:
        raise ValueError("No analysis scripts selected")

    latest_stats = read_latest_pointer(paths.analysis_outputs_dir / "latest.json")
    written: dict[str, Path] = {}

    for script in scripts:
        output = script.build(dataframe, run_context, manifest["run_id"])
        output_path = paths.analysis_artifacts_outputs_dir / f"{script.script_id}_{run_context.run_id}.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
            handle.write("\n")
        latest_stats[script.script_id] = output_path.relative_to(paths.analysis_outputs_dir).as_posix()
        written[script.script_id] = output_path

    analysis_manifest_path = paths.analysis_manifests_outputs_dir / f"analysis_manifest_{run_context.run_id}.json"
    with analysis_manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "run_id": run_context.run_id,
                "run_datetime": run_context.run_datetime,
                "manifest_run_id": manifest["run_id"],
                "scripts": sorted(written),
                "artifacts": {
                    script_id: path.relative_to(paths.analysis_outputs_dir).as_posix()
                    for script_id, path in written.items()
                },
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    write_latest_pointer(paths.analysis_outputs_dir / "latest.json", latest_stats)
    return written


def run_parameterized_analysis(template_id: str, parameters: dict[str, object]) -> Path:
    paths = ProjectPaths.discover()
    paths.ensure_runtime_dirs()
    dataframe, manifest = load_latest_clean_dataframe(paths)
    run_context = RunContext.now()
    output = run_analysis_template(template_id, parameters, dataframe, run_context, manifest["run_id"])
    script_id = str(output["script_id"])
    output_path = paths.analysis_artifacts_outputs_dir / f"{script_id}_{run_context.run_id}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")

    analysis_manifest_path = paths.analysis_manifests_outputs_dir / f"analysis_manifest_{run_context.run_id}.json"
    with analysis_manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "run_id": run_context.run_id,
                "run_datetime": run_context.run_datetime,
                "manifest_run_id": manifest["run_id"],
                "template_id": template_id,
                "parameters": parameters,
                "scripts": [script_id],
                "artifacts": {
                    script_id: output_path.relative_to(paths.analysis_outputs_dir).as_posix(),
                },
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    latest_stats = read_latest_pointer(paths.analysis_outputs_dir / "latest.json")
    latest_stats[script_id] = output_path.relative_to(paths.analysis_outputs_dir).as_posix()
    write_latest_pointer(paths.analysis_outputs_dir / "latest.json", latest_stats)
    return output_path

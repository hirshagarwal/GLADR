"""Histology report ingestion stage."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from gladr.core.latest_pointer import write_latest_pointer
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import RunContext
from gladr.ingestion.helpers.extract_histology import build_report


K_NUMBER_PATTERN = re.compile(r"(K\d+)", flags=re.IGNORECASE)
HISTOLOGY_COLUMNS = ["k_number", "marker", "value", "notes"]


def run_histology_ingestion(
    *,
    txt_dir: str | Path | None = None,
    csv_dir: str | Path | None = None,
    output_file: str | Path | None = None,
    csv_override: bool = False,
    generate_reports: bool = True,
    model: str = "gpt-5-nano",
    paths: ProjectPaths | None = None,
) -> dict[str, Path]:
    """Generate per-report marker CSVs and compile them into one histology dataset."""
    project_paths = paths or ProjectPaths.discover()
    project_paths.ensure_runtime_dirs()
    run_context = RunContext.now()

    histology_txt_dir = _resolve_project_path(
        txt_dir,
        default=project_paths.histology_text_reports_dir,
        project_root=project_paths.root,
    )
    histology_csv_dir = _resolve_project_path(
        csv_dir,
        default=project_paths.histology_marker_csv_dir,
        project_root=project_paths.root,
    )
    output_path = _resolve_project_path(
        output_file,
        default=project_paths.histology_datasets_outputs_dir / f"histology_dataset_{run_context.run_id}.json",
        project_root=project_paths.root,
    )
    manifest_path = project_paths.histology_manifests_outputs_dir / f"manifest_{run_context.run_id}.json"
    report_path = project_paths.histology_reports_outputs_dir / f"extraction_report_{run_context.run_id}.json"

    text_files = sorted(path for path in histology_txt_dir.glob("*.txt") if path.is_file())
    if not text_files:
        raise FileNotFoundError(f"No histology text files found in {histology_txt_dir}")

    csv_paths: list[Path] = []
    missing_csvs: list[Path] = []
    for text_file in text_files:
        extract_k_number(text_file)
        expected_csv = histology_csv_dir / f"{text_file.stem}.csv"
        if generate_reports:
            csv_paths.append(
                build_report(
                    text_file,
                    csv_override=csv_override,
                    model=model,
                    txt_dir=histology_txt_dir,
                    csv_dir=histology_csv_dir,
                )
            )
            continue

        if expected_csv.exists():
            csv_paths.append(expected_csv)
        else:
            missing_csvs.append(expected_csv)

    if not csv_paths:
        raise FileNotFoundError(f"No histology CSV files found in {histology_csv_dir}")

    combined = compile_histology_csvs(csv_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_histology_dataset(
        output_path,
        combined,
        run_id=run_context.run_id,
        run_datetime=run_context.run_datetime,
        source_csvs=len(csv_paths),
        missing_csvs=len(missing_csvs),
    )
    _write_json(
        manifest_path,
        {
            "run_id": run_context.run_id,
            "run_datetime": run_context.run_datetime,
            "source": "histology",
            "summary": {
                "text_reports": len(text_files),
                "source_csvs": len(csv_paths),
                "missing_csvs": len(missing_csvs),
                "total_rows": int(len(combined)),
                "generated_reports": bool(generate_reports),
            },
            "steps": [
                {
                    "step_id": "read_text_reports",
                    "label": "Read histology text reports",
                    "summary": f"{len(text_files)} text report(s) discovered",
                    "status": "completed",
                    "execution_mode": "static_code",
                    "inputs": [path.name for path in text_files],
                    "outputs": ["report text"],
                    "metrics": {"text_reports": len(text_files)},
                },
                {
                    "step_id": "extract_marker_csvs",
                    "label": "Extract marker CSVs",
                    "summary": f"{len(csv_paths)} marker CSV(s) available, {len(missing_csvs)} missing",
                    "status": "completed",
                    "execution_mode": "llm_powered" if generate_reports else "static_code",
                    "inputs": ["report text"],
                    "outputs": [path.name for path in csv_paths],
                    "metrics": {
                        "source_csvs": len(csv_paths),
                        "missing_csvs": len(missing_csvs),
                        "generated_reports": bool(generate_reports),
                    },
                },
                {
                    "step_id": "compile_histology_dataset",
                    "label": "Compile histology dataset",
                    "summary": f"{int(len(combined))} marker row(s)",
                    "status": "completed",
                    "execution_mode": "static_code",
                    "inputs": [path.name for path in csv_paths],
                    "outputs": [output_path.name],
                    "metrics": {"total_rows": int(len(combined))},
                },
            ],
            "text_reports_dir": histology_txt_dir.relative_to(project_paths.root).as_posix()
            if histology_txt_dir.is_relative_to(project_paths.root)
            else str(histology_txt_dir),
            "marker_csv_dir": histology_csv_dir.relative_to(project_paths.root).as_posix()
            if histology_csv_dir.is_relative_to(project_paths.root)
            else str(histology_csv_dir),
            "text_reports": len(text_files),
            "source_csvs": len(csv_paths),
            "missing_csvs": len(missing_csvs),
            "total_rows": int(len(combined)),
        },
    )
    _write_json(
        report_path,
        {
            "run_id": run_context.run_id,
            "run_datetime": run_context.run_datetime,
            "generated_reports": bool(generate_reports),
            "csv_override": bool(csv_override),
            "model": model if generate_reports else None,
            "processed_csvs": [path.name for path in csv_paths],
            "missing_csvs": [path.name for path in missing_csvs],
        },
    )

    write_latest_pointer(
        project_paths.histology_ingestion_outputs_dir / "latest.json",
        {
            "histology_dataset": _relative_to_or_name(output_path, project_paths.histology_ingestion_outputs_dir),
            "manifest": _relative_to_or_name(manifest_path, project_paths.histology_ingestion_outputs_dir),
            "extraction_report": _relative_to_or_name(report_path, project_paths.histology_ingestion_outputs_dir),
            "rows": int(len(combined)),
            "source_csvs": len(csv_paths),
            "missing_csvs": len(missing_csvs),
        },
    )

    return {
        "histology_dataset": output_path,
        "manifest": manifest_path,
        "extraction_report": report_path,
    }


def compile_histology_csvs(csv_paths: list[Path]) -> pd.DataFrame:
    """Read per-report marker CSVs and return a single dataframe with k_number."""
    frames: list[pd.DataFrame] = []
    for csv_path in sorted(csv_paths):
        k_number = extract_k_number(csv_path)
        frame = pd.read_csv(csv_path, dtype=str).fillna("")
        frame.columns = [column.strip() for column in frame.columns]
        if "notes" not in frame.columns:
            frame["notes"] = ""

        required_columns = {"marker", "value", "notes"}
        missing_columns = required_columns.difference(frame.columns)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"{csv_path} is missing required columns: {missing}")

        frame = frame[["marker", "value", "notes"]].copy()
        frame.insert(0, "k_number", k_number)
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=HISTOLOGY_COLUMNS)
    return pd.concat(frames, ignore_index=True)[HISTOLOGY_COLUMNS]


def extract_k_number(path: str | Path) -> str:
    """Extract a K-prefixed numeric identifier from a report filename."""
    match = K_NUMBER_PATTERN.search(Path(path).stem)
    if not match:
        raise ValueError(f"Could not extract K-number identifier from filename: {path}")
    return match.group(1).upper()


def _write_histology_dataset(
    output_path: Path,
    dataframe: pd.DataFrame,
    *,
    run_id: str,
    run_datetime: str,
    source_csvs: int,
    missing_csvs: int,
) -> None:
    if output_path.suffix.lower() == ".csv":
        dataframe.to_csv(output_path, index=False)
        return

    payload = {
        "run_id": run_id,
        "run_datetime": run_datetime,
        "source_csvs": source_csvs,
        "missing_csvs": missing_csvs,
        "total_rows": int(len(dataframe)),
        "records": dataframe.to_dict(orient="records"),
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _relative_to_or_name(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _resolve_project_path(value: str | Path | None, *, default: Path, project_root: Path) -> Path:
    if value is None:
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path

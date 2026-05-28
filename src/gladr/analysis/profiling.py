"""Dataset profiling helpers for analysis setup."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from gladr.core.latest_pointer import read_latest_pointer
from gladr.core.paths import ProjectPaths


def load_latest_clean_dataframe(paths: ProjectPaths | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    project_paths = paths or ProjectPaths.discover()
    latest_clean = read_latest_pointer(project_paths.registry_ingestion_outputs_dir / "latest.json")
    clean_dataset = latest_clean.get("clean_dataset")
    manifest_filename = latest_clean.get("manifest") or latest_clean.get("run_manifest")
    if not clean_dataset or not manifest_filename:
        raise FileNotFoundError("No clean dataset latest pointer found. Run ingestion first.")

    clean_path = project_paths.registry_ingestion_outputs_dir / str(clean_dataset)
    manifest_path = project_paths.registry_ingestion_outputs_dir / str(manifest_filename)
    with clean_path.open("r", encoding="utf-8") as handle:
        clean_payload = json.load(handle)
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    return pd.DataFrame(clean_payload["records"]), manifest


def build_dataset_profile(paths: ProjectPaths | None = None) -> dict[str, Any]:
    try:
        dataframe, manifest = load_latest_clean_dataframe(paths)
    except FileNotFoundError:
        return {"dataset": None, "variables": []}

    variables = [_profile_series(name, dataframe[name]) for name in dataframe.columns]
    return {
        "dataset": {
            "run_id": manifest.get("run_id"),
            "run_datetime": manifest.get("run_datetime"),
            "rows": int(len(dataframe)),
            "columns": int(len(dataframe.columns)),
        },
        "variables": variables,
    }


def _profile_series(name: str, series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    unique_count = _unique_count(non_null)
    missing = int(series.isna().sum())
    variable_type = _infer_variable_type(name, non_null, unique_count, len(series))
    profile: dict[str, Any] = {
        "name": name,
        "type": variable_type,
        "non_null": int(non_null.shape[0]),
        "missing": missing,
        "missing_pct": round((missing / len(series)) * 100, 1) if len(series) else 0,
        "unique_count": unique_count,
        "sample_values": [_json_safe(value) for value in non_null.head(4).tolist()],
        "present_rows": [int(index) for index in series[series.notna()].index.tolist()],
        "is_binary": _is_binary(non_null),
        "is_numeric": bool(pd.api.types.is_numeric_dtype(non_null)),
    }

    if pd.api.types.is_numeric_dtype(non_null):
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if not numeric.empty:
            profile["numeric_summary"] = {
                "min": _round_float(numeric.min()),
                "median": _round_float(numeric.median()),
                "max": _round_float(numeric.max()),
            }

    value_counts = non_null.astype(str).value_counts()
    top_values = value_counts.head(5)
    profile["top_values"] = [
        {"value": _json_safe(value), "count": int(count)}
        for value, count in top_values.items()
    ]
    profile["value_counts"] = [
        {"value": _json_safe(value), "count": int(count)}
        for value, count in value_counts.head(100).items()
    ]
    profile["value_counts_truncated"] = int(value_counts.shape[0]) > 100
    return profile


def _infer_variable_type(name: str, non_null: pd.Series, unique_count: int, row_count: int) -> str:
    lowered_name = name.lower()
    if lowered_name.endswith("_id") or lowered_name in {"patient_id", "histo_report", "notes"}:
        return "identifier" if unique_count > max(row_count * 0.5, 1) else "text"
    if _is_binary(non_null):
        return "binary"
    if pd.api.types.is_bool_dtype(non_null):
        return "binary"
    if pd.api.types.is_numeric_dtype(non_null):
        return "numeric"
    if "date" in lowered_name or lowered_name in {"dob", "dod"}:
        return "date"
    if unique_count <= 20:
        return "categorical"
    return "text"


def _is_binary(non_null: pd.Series) -> bool:
    values = {_normalize_binary_value(value) for value in non_null.tolist()}
    values.discard(None)
    return 1 < len(values) <= 2


def _normalize_binary_value(value: object) -> object | None:
    if _is_missing(value):
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) in {0.0, 1.0}:
            return int(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "false", "yes", "no", "y", "n", "0", "1", "m", "f"}:
        return normalized
    leading_token = normalized.replace("–", "-").replace("—", "-").split(maxsplit=1)[0].strip(":-;,.")
    if leading_token in {"true", "false", "yes", "no", "y", "n", "0", "1", "m", "f"}:
        return leading_token
    return str(value)


def _round_float(value: object) -> float:
    return round(float(value), 3)


def _json_safe(value: object) -> object:
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(inner_value) for key, inner_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(inner_value) for inner_value in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def _unique_count(series: pd.Series) -> int:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return len({_hashable_value(value) for value in series.tolist() if not _is_missing(value)})


def _hashable_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _hashable_value(inner_value)) for key, inner_value in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_hashable_value(inner_value) for inner_value in value)
    return value


def _is_missing(value: object) -> bool:
    if isinstance(value, (dict, list, tuple, set)):
        return False
    return bool(pd.isna(value))

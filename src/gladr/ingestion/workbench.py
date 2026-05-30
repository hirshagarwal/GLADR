"""Workbench helpers for inspecting, previewing, and running ingestion specs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd

from gladr.contracts import load_contract
from gladr.core.discovery import filter_by_ids, instantiate_discovered
from gladr.core.paths import ProjectPaths
from gladr.ingestion.adapters.base_adapter import BaseAdapter
from gladr.ingestion.normalizers import normalize_missing
from gladr.ingestion.runner import run_ingestion
from gladr.ingestion.spec_engine import operation_library


def build_ingestion_workbench_payload(paths: ProjectPaths | None = None) -> dict[str, Any]:
    project_paths = paths or ProjectPaths.discover()
    adapters = instantiate_discovered("gladr.ingestion.adapters", BaseAdapter)
    adapter_payloads = [_adapter_payload(adapter, project_paths) for adapter in adapters]
    return {
        "adapters": [
            payload
            for adapter, payload in zip(adapters, adapter_payloads, strict=False)
            if _should_publish_adapter(adapter, payload)
        ],
        "canonical_fields": load_contract("canonical_schema.json")["fields"],
        "data_files": discover_data_files(project_paths),
    }


def discover_data_files(paths: ProjectPaths | None = None) -> list[dict[str, Any]]:
    project_paths = paths or ProjectPaths.discover()
    candidates: list[tuple[str, Path, str]] = []
    candidates.extend(("Histology dataset", path, "histology_dataset") for path in project_paths.histology_datasets_outputs_dir.glob("*.json"))
    candidates.extend(("Canonical clean dataset", path, "canonical_dataset") for path in project_paths.canonical_datasets_outputs_dir.glob("*.json"))
    candidates.extend(("Reference data", path, "reference") for path in project_paths.reference_data_dir.glob("*.json"))
    candidates.extend(("Histology marker CSV", path, "histology_marker_csv") for path in project_paths.histology_marker_csv_dir.glob("*.csv"))

    latest_histology = _latest_file(project_paths.histology_ingestion_outputs_dir / "latest.json", project_paths.histology_ingestion_outputs_dir, "histology_dataset")
    latest_canonical = _latest_file(project_paths.canonical_ingestion_outputs_dir / "latest.json", project_paths.canonical_ingestion_outputs_dir, "clean_dataset")

    files = []
    seen: set[Path] = set()
    for label, path, kind in sorted(candidates, key=lambda item: (item[2], item[1].name)):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(
            {
                "label": label,
                "name": path.name,
                "path": _relative(project_paths, path),
                "kind": kind,
                "rows": _data_file_row_count(path),
                "columns": _data_file_columns(path),
                "column_values": _data_file_column_values(path),
                "is_latest": resolved in {item.resolve() for item in (latest_histology, latest_canonical) if item},
            }
        )
    return files


def preview_ingestion_spec(
    adapter_id: str,
    source_file: str | None,
    spec: dict[str, Any] | None,
    *,
    paths: ProjectPaths | None = None,
    row_limit: int = 10,
) -> dict[str, Any]:
    project_paths = paths or ProjectPaths.discover()
    adapter = _get_adapter(adapter_id)
    source_path = _resolve_source_file(project_paths, adapter, source_file)
    raw = adapter.load_raw(source_path)
    active_spec = _active_spec(adapter, spec, project_paths)
    result = adapter.transform(raw, source_path, spec=active_spec, paths=project_paths)
    transformed = result.dataframe

    return {
        "adapter_id": adapter.adapter_id,
        "source_file": _relative(project_paths, source_path),
        "source_profile": _profile_dataframe(raw),
        "transformed_profile": _profile_dataframe(transformed),
        "summary": result.source_summary,
        "steps": [step.to_manifest() if hasattr(step, "to_manifest") else step for step in result.steps],
        "quality_report": result.ingestion_report[:row_limit],
        "rows": _records(transformed.head(row_limit)),
    }


def run_ingestion_spec_from_ui(
    adapter_id: str,
    source_file: str | None,
    spec: dict[str, Any] | None,
    *,
    paths: ProjectPaths | None = None,
) -> dict[str, Path]:
    project_paths = paths or ProjectPaths.discover()
    adapter = _get_adapter(adapter_id)
    source_path = _resolve_source_file(project_paths, adapter, source_file)
    active_spec = _active_spec(adapter, spec, project_paths)
    active_spec["transient"] = True
    written = run_ingestion(adapter_id=adapter.adapter_id, source_file=str(source_path), spec=active_spec, paths=project_paths)
    _save_default_spec(adapter, active_spec, project_paths)
    return written


def _adapter_payload(adapter: BaseAdapter, paths: ProjectPaths) -> dict[str, Any]:
    files = adapter.match_files(paths.root)
    default_spec, default_spec_source = _default_spec_for_adapter(adapter, paths)
    source_files = [
        {
            "name": path.name,
            "path": _relative(paths, path),
            "rows": _safe_row_count(adapter, path),
            "columns": _safe_columns(adapter, path),
        }
        for path in files
    ]
    default_spec = _workbench_default_spec(adapter, default_spec, default_spec_source, source_files)
    return {
        "adapter_id": adapter.adapter_id,
        "source_glob": adapter.source_glob,
        "default_spec_id": adapter.default_spec_id,
        "default_spec": default_spec,
        "default_spec_source": default_spec_source,
        "operations": operation_library(adapter),
        "source_files": source_files,
        "field_options": _field_options(default_spec, source_files),
    }


def _should_publish_adapter(adapter: BaseAdapter, payload: dict[str, Any]) -> bool:
    if payload.get("source_files"):
        return True
    if payload.get("default_spec_source") == "saved":
        return True
    return bool(getattr(adapter, "publish_without_matches", False))


def _workbench_default_spec(
    adapter: BaseAdapter,
    default_spec: dict[str, Any] | None,
    default_spec_source: str,
    source_files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if adapter.adapter_id != "generic_csv" or default_spec_source != "packaged":
        return default_spec
    columns = [str(column) for column in (source_files[0].get("columns", []) if source_files else []) if str(column)]
    return _with_identity_column_mapping(default_spec, columns)


def _with_identity_column_mapping(default_spec: dict[str, Any] | None, columns: list[str]) -> dict[str, Any] | None:
    active = copy.deepcopy(default_spec)
    if not isinstance(active, dict) or not columns:
        return active

    steps = active.get("steps")
    if not isinstance(steps, list):
        steps = []
    if any(isinstance(step, dict) and step.get("operation") in {"rename_columns", "map_columns"} for step in steps):
        active["steps"] = steps
        return active

    identity_step = {
        "id": "identity_column_mapping",
        "operation": "rename_columns",
        "label": "Map source columns",
        "description": "Default one-to-one source column to output column mapping for generic CSV imports.",
        "outputs": ["mapped columns"],
        "params": {"columns": {column: column for column in columns}},
    }
    finalize_index = next(
        (index for index, step in enumerate(steps) if isinstance(step, dict) and step.get("operation") == "finalize_output"),
        len(steps),
    )
    active["steps"] = [*steps[:finalize_index], identity_step, *steps[finalize_index:]]
    return active


def _get_adapter(adapter_id: str) -> BaseAdapter:
    adapters = instantiate_discovered("gladr.ingestion.adapters", BaseAdapter)
    selected = filter_by_ids(adapters, {adapter_id}, "adapter_id")
    if not selected:
        raise ValueError(f"Unknown ingestion adapter: {adapter_id}")
    return selected[0]


def _active_spec(adapter: BaseAdapter, spec: dict[str, Any] | None, paths: ProjectPaths) -> dict[str, Any]:
    default_spec, _ = _default_spec_for_adapter(adapter, paths)
    active = copy.deepcopy(spec or default_spec)
    if not isinstance(active, dict):
        raise ValueError("Ingestion spec must be a JSON object.")
    spec_adapter = active.get("adapter_id")
    if spec_adapter and spec_adapter != adapter.adapter_id:
        raise ValueError(f"Spec adapter_id {spec_adapter} does not match adapter {adapter.adapter_id}.")
    active["adapter_id"] = adapter.adapter_id
    active["transient"] = True
    return active


def _default_spec_for_adapter(adapter: BaseAdapter, paths: ProjectPaths) -> tuple[dict[str, Any], str]:
    saved_path = _saved_default_spec_path(paths, adapter)
    try:
        saved_spec = json.loads(saved_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return adapter.default_spec(), "packaged"
    except (OSError, json.JSONDecodeError, ValueError):
        return adapter.default_spec(), "packaged"
    if not isinstance(saved_spec, dict):
        return adapter.default_spec(), "packaged"
    spec_adapter = saved_spec.get("adapter_id")
    if spec_adapter and spec_adapter != adapter.adapter_id:
        return adapter.default_spec(), "packaged"
    active = copy.deepcopy(saved_spec)
    active["adapter_id"] = adapter.adapter_id
    active.pop("transient", None)
    return active, "saved"


def _save_default_spec(adapter: BaseAdapter, spec: dict[str, Any], paths: ProjectPaths) -> Path:
    saved_spec = copy.deepcopy(spec)
    saved_spec["adapter_id"] = adapter.adapter_id
    saved_spec.pop("transient", None)
    saved_path = _saved_default_spec_path(paths, adapter)
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text(json.dumps(saved_spec, indent=2) + "\n", encoding="utf-8")
    return saved_path


def _saved_default_spec_path(paths: ProjectPaths, adapter: BaseAdapter) -> Path:
    return paths.ingestion_specs_dir / f"{adapter.adapter_id}.json"


def _resolve_source_file(paths: ProjectPaths, adapter: BaseAdapter, source_file: str | None) -> Path:
    matched = adapter.match_files(paths.root)
    if not matched:
        raise FileNotFoundError(f"No source files found for adapter {adapter.adapter_id}.")
    if not source_file:
        return matched[0]

    candidate = paths.root / source_file
    if Path(source_file).is_absolute():
        candidate = Path(source_file)
    resolved = candidate.resolve()
    root = paths.root.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Source file must be inside the GLADR workspace.")
    if resolved not in [path.resolve() for path in matched]:
        raise ValueError(f"Source file is not matched by adapter {adapter.adapter_id}: {source_file}")
    return resolved


def _profile_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(dataframe)),
        "columns": int(len(dataframe.columns)),
        "variables": [_profile_series(name, dataframe[name]) for name in dataframe.columns],
    }


def _profile_series(name: str, series: pd.Series) -> dict[str, Any]:
    present_mask = ~series.apply(_is_missing)
    present = series[present_mask]
    missing = int((~present_mask).sum())
    value_counts = present.astype(str).value_counts()
    top_values = value_counts.head(5)
    return {
        "name": name,
        "type": _infer_type(name, present),
        "non_null": int(present.shape[0]),
        "missing": missing,
        "missing_pct": round((missing / len(series)) * 100, 1) if len(series) else 0,
        "unique_count": _unique_count(present),
        "sample_values": [_json_safe(value) for value in present.head(4).tolist()],
        "top_values": [
            {"value": _json_safe(value), "count": int(count)}
            for value, count in top_values.items()
        ],
        "value_counts": [
            {"value": _json_safe(value), "count": int(count)}
            for value, count in value_counts.head(100).items()
        ],
        "value_counts_truncated": int(value_counts.shape[0]) > 100,
    }


def _infer_type(name: str, non_null: pd.Series) -> str:
    lowered = name.lower()
    if "date" in lowered or lowered in {"dob", "dod"}:
        return "date"
    if pd.api.types.is_numeric_dtype(non_null):
        return "numeric"
    unique_count = _unique_count(non_null)
    if unique_count <= 2 and unique_count > 0:
        return "binary-like"
    if unique_count <= 20:
        return "categorical"
    return "text"


def _unique_count(series: pd.Series) -> int:
    if series.empty:
        return 0
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return len({_hashable(value) for value in series.tolist() if not _is_missing(value)})


def _hashable(value: object) -> object:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _hashable(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_hashable(item) for item in value)
    return value


def _is_missing(value: object) -> bool:
    if isinstance(value, (dict, list, tuple, set)):
        return False
    return normalize_missing(value) is None


def _records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    safe = dataframe.astype(object).where(pd.notna(dataframe), None)
    return [
        {str(key): _json_safe(value) for key, value in record.items()}
        for record in safe.to_dict(orient="records")
    ]


def _json_safe(value: object) -> Any:
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _safe_row_count(adapter: BaseAdapter, path: Path) -> int | None:
    try:
        return int(len(adapter.load_raw(path)))
    except (OSError, ValueError):
        return None


def _safe_columns(adapter: BaseAdapter, path: Path) -> list[str]:
    try:
        return [str(column) for column in adapter.load_raw(path).columns]
    except (OSError, ValueError):
        return []


def _data_file_row_count(path: Path) -> int | None:
    try:
        if path.suffix.lower() == ".csv":
            return int(len(pd.read_csv(path)))
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("records"), list):
                return len(payload["records"])
            if isinstance(payload, list):
                return len(payload)
            return 1
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def _data_file_columns(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".csv":
            return [str(column) for column in pd.read_csv(path, nrows=0).columns]
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload.get("records") if isinstance(payload, dict) else payload
            if isinstance(records, list) and records:
                return sorted({str(key) for record in records if isinstance(record, dict) for key in record})
            if isinstance(payload, dict):
                return sorted(str(key) for key in payload)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return []


def _data_file_column_values(path: Path, *, limit: int = 200) -> dict[str, list[str]]:
    try:
        dataframe = _read_data_file_frame(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    values: dict[str, list[str]] = {}
    for column in dataframe.columns:
        present = dataframe[column][~dataframe[column].apply(_is_missing)]
        if present.empty:
            continue
        unique = sorted({str(value) for value in present.tolist() if str(value)})
        values[str(column)] = unique[:limit]
    return values


def _read_data_file_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            records = payload.get("records")
            if isinstance(records, list):
                return pd.DataFrame.from_records(records)
            return pd.DataFrame([payload])
        if isinstance(payload, list):
            return pd.DataFrame.from_records(payload)
    raise ValueError(f"Unsupported data file type: {path.suffix}")


def _field_options(default_spec: dict[str, Any] | None, source_files: list[dict[str, Any]]) -> list[str]:
    fields: set[str] = set()
    fields.update(field["name"] for field in load_contract("canonical_schema.json")["fields"])
    for source_file in source_files:
        fields.update(str(column) for column in source_file.get("columns", []))
    fields.update(_fields_from_spec(default_spec or {}))
    return sorted(field for field in fields if field)


def _fields_from_spec(value: Any, parent_key: str | None = None) -> set[str]:
    field_keys = {
        "field",
        "fields",
        "columns",
        "source",
        "target",
        "output",
        "inputs",
        "outputs",
        "id_column",
        "left_key",
        "right_key",
        "left_field",
        "right_field",
        "numerator",
        "denominator",
        "dob",
        "presentation_date",
    }
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():
            if key in field_keys:
                found.update(_field_values(item))
            found.update(_fields_from_spec(item, key))
        return found
    if isinstance(value, list):
        return {field for item in value for field in _fields_from_spec(item, parent_key)}
    return set()


def _field_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, dict):
        return {str(item) for pair in value.items() for item in pair if item}
    if isinstance(value, list):
        return {field for item in value for field in _field_values(item)}
    return set()


def _latest_file(pointer_path: Path, root: Path, key: str) -> Path | None:
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    filename = payload.get(key)
    if not filename:
        return None
    return root / str(filename)


def _relative(paths: ProjectPaths, path: Path) -> str:
    try:
        return path.relative_to(paths.root).as_posix()
    except ValueError:
        return path.name

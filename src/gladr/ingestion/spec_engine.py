"""Executable ingestion specs for adapter-owned transform chains."""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd

from gladr.contracts import canonical_field_names
from gladr.core.paths import ProjectPaths
from gladr.ingestion.adapters.base_adapter import AdapterRunResult, BaseAdapter, IngestionStep
from gladr.ingestion.normalizers import (
    compute_age_years,
    compute_nlr,
    normalize_boolean,
    normalize_category,
    normalize_text,
    parse_date,
    safe_float,
)
from gladr.ingestion.quality_flags import unique_flags
from gladr.ingestion.validators import is_stub_row


OPERATION_LIBRARY: list[dict[str, Any]] = [
    {
        "operation": "rename_columns",
        "label": "Rename Columns",
        "category": "Structure",
        "description": "Rename source columns into GLADR working field names. Columns not listed are kept unchanged.",
        "schema": {
            "expects": ["source columns"],
            "produces": ["renamed columns"],
            "config": [{"name": "columns", "kind": "mapping", "label": "Source to output columns"}],
        },
    },
    {
        "operation": "filter_rows",
        "label": "Filter Rows",
        "category": "Quality",
        "description": "Keep or drop rows using reusable field conditions and populated-field thresholds.",
        "schema": {
            "expects": ["working dataframe", "filter conditions"],
            "produces": ["filtered rows"],
            "config": [
                {"name": "action", "kind": "choice", "label": "Action", "choices": ["keep", "drop"]},
                {"name": "match", "kind": "choice", "label": "Match", "choices": ["all", "any"]},
                {"name": "conditions", "kind": "filter_conditions", "label": "Conditions"},
                {"name": "minimum_populated_fields", "kind": "number", "label": "Minimum populated fields"},
                {"name": "ignored_fields", "kind": "fields", "label": "Ignored fields"},
            ],
        },
    },
    {
        "operation": "normalize_fields",
        "label": "Normalize Fields",
        "category": "Normalize",
        "description": "Convert one or more fields to text, category, boolean, date, or number outputs with explicit invalid-value handling.",
        "schema": {
            "expects": ["source fields"],
            "produces": ["normalized output fields", "optional invalid-value flags"],
            "config": [{"name": "fields", "kind": "normalization_fields", "label": "Field normalizations"}],
        },
    },
    {
        "operation": "lookup_mapping",
        "label": "Lookup Mapping",
        "category": "Normalize",
        "description": "Map source values through a reference JSON lookup table.",
        "schema": {
            "expects": ["fields", "mapping JSON file"],
            "produces": ["mapped field values"],
            "config": [
                {"name": "fields", "kind": "fields", "label": "Fields"},
                {"name": "mapping_file", "kind": "file", "label": "Mapping file"},
            ],
        },
    },
    {
        "operation": "remap_values",
        "label": "Remap Values",
        "category": "Normalize",
        "description": "Replace values in one field using inline key/value mappings.",
        "schema": {
            "expects": ["selected field", "inline key/value mappings"],
            "produces": ["remapped field values"],
            "config": [
                {"name": "field", "kind": "field", "label": "Field"},
                {"name": "value_mappings", "kind": "value_mappings", "label": "Value mappings"},
                {"name": "case_sensitive", "kind": "boolean", "label": "Case sensitive"},
            ],
        },
    },
    {
        "operation": "derive_age",
        "label": "Derive Age",
        "category": "Derive",
        "description": "Use a source age when present, otherwise compute age from birth and presentation dates.",
        "schema": {
            "expects": ["source age field", "date of birth field", "presentation date field"],
            "produces": ["age output field", "optional missing-age flag"],
            "config": [
                {"name": "source", "kind": "field", "label": "Source age"},
                {"name": "dob", "kind": "field", "label": "Date of birth"},
                {"name": "presentation_date", "kind": "field", "label": "Presentation date"},
                {"name": "output", "kind": "field", "label": "Output"},
                {"name": "missing_flag", "kind": "text", "label": "Missing flag"},
            ],
        },
    },
    {
        "operation": "compute_ratio",
        "label": "Compute Ratio",
        "category": "Derive",
        "description": "Compute one numeric ratio from two numeric variables.",
        "schema": {
            "expects": ["numeric numerator", "numeric denominator"],
            "produces": ["ratio output field"],
            "config": [
                {"name": "numerator", "kind": "field", "label": "Numerator"},
                {"name": "denominator", "kind": "field", "label": "Denominator"},
                {"name": "output", "kind": "field", "label": "Output"},
            ],
        },
    },
    {
        "operation": "math",
        "label": "Math",
        "category": "Derive",
        "description": "Apply basic numeric math to fields or literal values.",
        "schema": {
            "expects": ["numeric fields or literal values"],
            "produces": ["numeric output field"],
            "config": [
                {"name": "operator", "kind": "choice", "label": "Operator", "choices": ["add", "subtract", "multiply", "divide"]},
                {"name": "left_field", "kind": "field", "label": "Left field"},
                {"name": "left_value", "kind": "number", "label": "Left value"},
                {"name": "right_field", "kind": "field", "label": "Right field"},
                {"name": "right_value", "kind": "number", "label": "Right value"},
                {"name": "output", "kind": "field", "label": "Output"},
                {"name": "precision", "kind": "number", "label": "Precision"},
            ],
        },
    },
    {
        "operation": "join_data_file",
        "label": "Join Data File",
        "category": "Combine",
        "description": "Join the current rows to another workspace data file, optionally pivoting long-form marker data first.",
        "schema": {
            "expects": ["current rows", "workspace data file", "left key", "right key"],
            "produces": ["current rows with joined columns"],
            "config": [
                {"name": "file", "kind": "data_file", "label": "Data file"},
                {"name": "left_key", "kind": "field", "label": "Left key"},
                {"name": "right_key", "kind": "field", "label": "Right key"},
                {"name": "join_type", "kind": "choice", "label": "Join type", "choices": ["left", "inner", "outer"]},
                {"name": "columns", "kind": "fields", "label": "Columns"},
                {"name": "right_prefix", "kind": "text", "label": "Output prefix"},
                {"name": "pivot.index", "kind": "field", "label": "Pivot index"},
                {"name": "pivot.columns", "kind": "field", "label": "Pivot columns"},
                {"name": "pivot.values", "kind": "field", "label": "Pivot values"},
            ],
        },
    },
    {
        "operation": "static_code",
        "label": "Static Code",
        "category": "Code",
        "description": "Run an adapter-allowlisted Python transform for source-specific logic.",
        "schema": {
            "expects": ["allowlisted Python function", "input fields"],
            "produces": ["function-defined output fields"],
            "config": [
                {"name": "function", "kind": "static_function", "label": "Function"},
                {"name": "inputs", "kind": "fields", "label": "Inputs"},
                {"name": "outputs", "kind": "fields", "label": "Outputs"},
            ],
        },
    },
    {
        "operation": "finalize_output",
        "label": "Finalize Output",
        "category": "Structure",
        "description": "Clean up the output dataset by dropping helper fields and optionally placing canonical fields first.",
        "schema": {
            "expects": ["working dataframe"],
            "produces": ["clean output fields"],
            "config": [
                {"name": "drop_fields", "kind": "fields", "label": "Drop fields"},
                {"name": "canonical_fields_first", "kind": "boolean", "label": "Canonical fields first"},
                {"name": "add_missing_canonical_fields", "kind": "boolean", "label": "Add missing canonical fields"},
            ],
        },
    },
]


def load_default_spec(adapter_id: str) -> dict[str, Any]:
    source = resources.files("gladr.ingestion.specs").joinpath(f"{adapter_id}.json")
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def operation_library(adapter: BaseAdapter | None = None) -> list[dict[str, Any]]:
    operations = copy.deepcopy(OPERATION_LIBRARY)
    if adapter:
        static_code = next((item for item in operations if item["operation"] == "static_code"), None)
        if static_code is not None:
            static_code["functions"] = adapter.custom_operation_definitions()
    return operations


def execute_ingestion_spec(
    adapter: BaseAdapter,
    dataframe: pd.DataFrame,
    source_path: Path,
    spec: dict[str, Any],
    *,
    paths: ProjectPaths | None = None,
) -> AdapterRunResult:
    project_paths = paths or ProjectPaths.discover()
    working = dataframe.copy()
    raw_rows = len(working)
    flags_by_index: dict[Any, list[str]] = {index: [] for index in working.index}
    flag_details_by_index: dict[Any, list[dict[str, Any]]] = {index: [] for index in working.index}
    stub_rows = 0
    steps: list[IngestionStep] = []

    for position, step in enumerate(spec.get("steps", []), start=1):
        if not isinstance(step, dict) or step.get("enabled") is False:
            continue
        before_rows = len(working)
        operation = str(step.get("operation") or "")
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        step_id = str(step.get("id") or f"{position}:{operation}")
        label = str(step.get("label") or _operation_label(operation))
        working, metrics = _apply_operation(
            adapter=adapter,
            dataframe=working,
            operation=operation,
            params=params,
            paths=project_paths,
            flags_by_index=flags_by_index,
            flag_details_by_index=flag_details_by_index,
            step_context={
                "step_id": f"{source_path.stem}:{step_id}",
                "step_label": label,
                "step_position": position,
                "operation": operation,
            },
        )
        if operation == "remove_stub_rows":
            stub_rows += int(metrics.get("stub_rows") or 0)
        if operation == "filter_rows" and params.get("counts_as") == "stub_rows":
            stub_rows += int(metrics.get("filtered_rows") or 0)

        summary = str(step.get("description") or _summarize_operation(operation, params, metrics, before_rows, len(working)))
        manifest_step = IngestionStep(
            step_id=f"{source_path.stem}:{step_id}",
            label=label,
            summary=summary,
            execution_mode="static_code",
            source_file=source_path.name,
            inputs=[str(value) for value in step.get("inputs", [])] if isinstance(step.get("inputs"), list) else [],
            outputs=[str(value) for value in step.get("outputs", [])] if isinstance(step.get("outputs"), list) else [],
            metrics={"operation": operation, **metrics},
        )
        steps.append(manifest_step)

    working["source"] = adapter.adapter_id
    working["data_quality_flags"] = [unique_flags(flags_by_index.get(index, [])) for index in working.index]

    patient_ids = working["patient_id"].tolist() if "patient_id" in working.columns else [None] * len(working)
    report = [
        {
            "patient_id": patient_id,
            "source_file": source_path.name,
            "flags": unique_flags(flags_by_index.get(index, [])),
            "flag_details": _unique_flag_details(flag_details_by_index.get(index, [])),
        }
        for index, patient_id in zip(working.index, patient_ids, strict=False)
    ]

    return AdapterRunResult(
        dataframe=working,
        ingestion_report=report,
        source_summary={
            "adapter": adapter.adapter_id,
            "file": source_path.name,
            "rows_raw": raw_rows,
            "rows_stub": stub_rows,
            "rows_ingested": len(working),
            "spec_id": spec.get("spec_id"),
            "spec_version": spec.get("version"),
        },
        steps=steps,
    )


def _apply_operation(
    *,
    adapter: BaseAdapter,
    dataframe: pd.DataFrame,
    operation: str,
    params: dict[str, Any],
    paths: ProjectPaths,
    flags_by_index: dict[Any, list[str]],
    flag_details_by_index: dict[Any, list[dict[str, Any]]],
    step_context: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    working = dataframe.copy()

    if operation in {"rename_columns", "map_columns"}:
        columns = params.get("columns") if isinstance(params.get("columns"), dict) else {}
        rename_map = {
            str(source): str(target)
            for source, target in columns.items()
            if source in working.columns and (str(target) not in working.columns or source == str(target))
        }
        return working.rename(columns=rename_map), {"mapped_columns": len(rename_map)}

    if operation == "validate_required_columns":
        required = [str(value) for value in params.get("columns", [])]
        missing = [field for field in required if field not in working.columns]
        return working, {"required_columns": len(required), "missing_columns": len(missing), "legacy_noop": True}

    if operation == "remove_stub_rows":
        id_column = str(params.get("id_column") or "patient_id")
        mask = working.apply(is_stub_row, axis=1, id_column=id_column)
        removed_indexes = set(working.index[mask])
        for index in removed_indexes:
            flags_by_index.pop(index, None)
            flag_details_by_index.pop(index, None)
        return working.loc[~mask].copy(), {"stub_rows": int(mask.sum()), "remaining_rows": int((~mask).sum())}

    if operation == "filter_rows":
        mask = _filter_mask(working, params)
        action = str(params.get("action") or "keep")
        keep_mask = ~mask if action == "drop" else mask
        removed_indexes = set(working.index[~keep_mask])
        for index in removed_indexes:
            flags_by_index.pop(index, None)
            flag_details_by_index.pop(index, None)
        return working.loc[keep_mask].copy(), {
            "filtered_rows": int((~keep_mask).sum()),
            "remaining_rows": int(keep_mask.sum()),
            "action": action,
            "filter_label": _filter_label(params),
            "filter_description": _filter_description(params),
            "filter_conditions": _filter_rule_summaries(params),
            "minimum_populated_fields": params.get("minimum_populated_fields"),
        }

    if operation == "normalize_text":
        fields = _fields(params)
        for field in fields:
            if field in working.columns:
                working[field] = working[field].apply(normalize_text)
        return working, {"fields": len(fields)}

    if operation == "normalize_category":
        fields = _fields(params)
        for field in fields:
            if field in working.columns:
                working[field] = working[field].apply(normalize_category)
        return working, {"fields": len(fields)}

    if operation == "normalize_boolean":
        fields = _fields(params)
        for field in fields:
            if field in working.columns:
                working[field] = working[field].apply(normalize_boolean)
        return working, {"fields": len(fields)}

    if operation == "normalize_fields":
        return _normalize_fields(working, params, flags_by_index, flag_details_by_index, step_context)

    if operation == "parse_date":
        mappings = params.get("mappings")
        if not isinstance(mappings, list):
            mappings = [{"source": field, "target": field} for field in _fields(params)]
        parsed_fields = 0
        invalid_values = 0
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            source = str(mapping.get("source") or "")
            target = str(mapping.get("target") or source)
            if source not in working.columns:
                continue
            original = working[source]
            parsed = original.apply(parse_date)
            working[target] = parsed
            flag = mapping.get("invalid_flag")
            if flag:
                for index, raw_value in original.items():
                    if normalize_text(raw_value) is not None and parsed.loc[index] is None:
                        _append_flag_detail(
                            flags_by_index,
                            flag_details_by_index,
                            index,
                            flag=str(flag),
                            step_context=step_context,
                            field=target,
                            source=source,
                            output=target,
                            raw_value=raw_value,
                            message=f"{target} could not be converted to a date.",
                            hint="Use a supported date value or update this step's date parsing rule.",
                        )
                        invalid_values += 1
            parsed_fields += 1
        return working, {"date_fields": parsed_fields, "invalid_values": invalid_values}

    if operation == "to_float":
        fields = _fields(params)
        for field in fields:
            if field in working.columns:
                working[field] = working[field].apply(safe_float)
        return working, {"fields": len(fields)}

    if operation == "lookup_mapping":
        fields = _fields(params)
        mapping_file = str(params.get("mapping_file") or "")
        mapping = json.loads((paths.root / mapping_file).read_text(encoding="utf-8")) if mapping_file else {}
        for field in fields:
            if field not in working.columns:
                continue
            working[field] = working[field].apply(
                lambda value: mapping.get(str(value).lower(), value) if value is not None else None
            )
        return working, {"fields": len(fields), "mapping_file": mapping_file}

    if operation == "remap_values":
        return _remap_values(working, params)

    if operation == "derive_age":
        output = str(params.get("output") or "age_at_presentation")
        source = str(params.get("source") or output)
        dob = str(params.get("dob") or "dob")
        presentation_date = str(params.get("presentation_date") or "presentation_date")
        missing_flag = params.get("missing_flag")

        def resolve(row: pd.Series) -> int | None:
            value = safe_float(row.get(source))
            if value is not None:
                return int(value)
            return compute_age_years(row.get(dob), row.get(presentation_date))

        working[output] = working.apply(resolve, axis=1)
        missing_count = 0
        if missing_flag:
            for index, value in working[output].items():
                if pd.isna(value):
                    row = working.loc[index]
                    _append_flag_detail(
                        flags_by_index,
                        flag_details_by_index,
                        index,
                        flag=str(missing_flag),
                        step_context=step_context,
                        field=output,
                        source=source,
                        output=output,
                        raw_value=row.get(source),
                        message=f"{output} could not be resolved from {source}, {dob}, and {presentation_date}.",
                        hint="Provide age directly or make sure date of birth and presentation date both parse correctly.",
                        context={
                            "source_value": _detail_value(row.get(source)),
                            "dob_value": _detail_value(row.get(dob)),
                            "presentation_date_value": _detail_value(row.get(presentation_date)),
                        },
                    )
                    missing_count += 1
        return working, {"missing_age_records": missing_count}

    if operation == "compute_ratio":
        output = str(params.get("output") or "")
        numerator = str(params.get("numerator") or "")
        denominator = str(params.get("denominator") or "")
        if output:
            working[output] = working.apply(lambda row: compute_nlr(row.get(numerator), row.get(denominator)), axis=1)
        return working, {"derived_fields": 1 if output else 0}

    if operation == "math":
        output = str(params.get("output") or "")
        if output:
            working[output] = working.apply(lambda row: _math_result(row, params), axis=1)
        return working, {"derived_fields": 1 if output else 0, "operator": params.get("operator") or "divide"}

    if operation == "join_data_file":
        joined = _join_data_file(working, params, paths)
        return joined, {
            "join_type": params.get("join_type") or "left",
            "left_key": params.get("left_key"),
            "right_key": params.get("right_key"),
            "file": params.get("file"),
            "input_rows": len(working),
            "output_rows": len(joined),
            "output_columns": len(joined.columns),
        }

    if operation == "derive_resection_type":
        source = str(params.get("source") or "resection_date")
        output = str(params.get("output") or "resection_type")
        working[output] = working[source].apply(lambda value: "Resection" if value else "Biopsy/None") if source in working else None
        return working, {"derived_fields": 1}

    if operation == "derive_recurrence_type":
        source = str(params.get("source") or "first_recurrence_evidence")
        output = str(params.get("output") or "recurrence_type")
        if source in working.columns:
            working[output] = working[source].apply(_derive_recurrence_type)
        return working, {"derived_fields": 1}

    if operation == "set_value":
        field = str(params.get("field") or "")
        if field:
            working[field] = params.get("value")
        return working, {"fields": 1 if field else 0}

    if operation in {"custom_python", "static_code"}:
        function_id = str(params.get("function") or "")
        updated = adapter.apply_custom_operation(function_id, working, params)
        return updated, {"function": function_id, "outputs": len(params.get("outputs", []))}

    if operation == "attach_quality_flags":
        working["data_quality_flags"] = [unique_flags(flags_by_index.get(index, [])) for index in working.index]
        flagged_records = sum(1 for flags in working["data_quality_flags"] if flags)
        return working, {"flagged_records": flagged_records}

    if operation == "finalize_output":
        if "source" not in working.columns:
            working["source"] = adapter.adapter_id
        working["data_quality_flags"] = [unique_flags(flags_by_index.get(index, [])) for index in working.index]
        return _finalize_output(working, params)

    if operation == "select_canonical_fields":
        strict_params = {
            "drop_fields": [],
            "canonical_fields_first": True,
            "add_missing_canonical_fields": True,
            "canonical_only": True,
        }
        return _finalize_output(working, strict_params)

    raise ValueError(f"Unsupported ingestion operation: {operation}")


def _finalize_output(dataframe: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    working = dataframe.copy()
    canonical_fields = canonical_field_names()

    if params.get("add_missing_canonical_fields", True):
        for field in canonical_fields:
            if field not in working.columns:
                working[field] = None

    drop_fields = set(_fields({"fields": params.get("drop_fields", [])}))
    keep_fields = [field for field in working.columns if field not in drop_fields]
    if params.get("canonical_only") is True:
        keep_fields = [field for field in canonical_fields if field in working.columns and field not in drop_fields]
    elif params.get("canonical_fields_first", True):
        canonical_first = [field for field in canonical_fields if field in keep_fields]
        extras = [field for field in keep_fields if field not in canonical_first]
        keep_fields = canonical_first + extras

    return working[keep_fields].copy(), {
        "output_fields": len(keep_fields),
        "dropped_fields": len(drop_fields),
        "canonical_fields": sum(1 for field in canonical_fields if field in keep_fields),
    }


def _remap_values(dataframe: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    working = dataframe.copy()
    field = str(params.get("field") or "")
    if field not in working.columns:
        return working, {"field": field, "mappings": 0, "remapped_values": 0, "missing_field": bool(field)}

    mapping = _value_mapping(params)
    case_sensitive = bool(params.get("case_sensitive"))
    keyed_mapping = {
        _mapping_key(source, case_sensitive): target
        for source, target in mapping.items()
        if _mapping_key(source, case_sensitive) is not None
    }
    if not keyed_mapping:
        return working, {"field": field, "mappings": 0, "remapped_values": 0}

    remapped_values = 0

    def remap(value: object) -> object:
        nonlocal remapped_values
        key = _mapping_key(value, case_sensitive)
        if key in keyed_mapping:
            remapped_values += 1
            return keyed_mapping[key]
        return value

    working[field] = working[field].apply(remap)
    return working, {"field": field, "mappings": len(keyed_mapping), "remapped_values": remapped_values}


def _value_mapping(params: dict[str, Any]) -> dict[object, object]:
    raw = params.get("value_mappings", params.get("mappings", {}))
    if isinstance(raw, dict):
        return {source: _remap_target(target) for source, target in raw.items()}
    if not isinstance(raw, list):
        return {}

    mapping: dict[object, object] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = item.get("key", item.get("from", item.get("source")))
        if source in (None, ""):
            continue
        mapping[source] = _remap_target(item.get("value", item.get("to", item.get("target", ""))))
    return mapping


def _remap_target(value: object) -> object | None:
    if value == "":
        return None
    return value


def _mapping_key(value: object, case_sensitive: bool) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    return normalized if case_sensitive else normalized.lower()


def _join_data_file(dataframe: pd.DataFrame, params: dict[str, Any], paths: ProjectPaths) -> pd.DataFrame:
    file_value = str(params.get("file") or "")
    left_key = str(params.get("left_key") or "")
    right_key = str(params.get("right_key") or "")
    join_type = str(params.get("join_type") or "left")
    if join_type not in {"left", "inner", "outer"}:
        raise ValueError(f"Unsupported join type: {join_type}")
    if not file_value:
        raise ValueError("Join step requires a data file.")
    if left_key not in dataframe.columns:
        raise ValueError(f"Join left key is not in the working dataset: {left_key}")

    right = _load_data_file(paths, file_value)
    pivot = params.get("pivot") if isinstance(params.get("pivot"), dict) else {}
    if pivot:
        right = _pivot_join_file(right, pivot)

    if right_key not in right.columns:
        raise ValueError(f"Join right key is not in the data file: {right_key}")

    selected_columns = [str(column) for column in params.get("columns", []) if str(column) in right.columns]
    if selected_columns:
        keep = list(dict.fromkeys([right_key, *selected_columns]))
        right = right[keep]

    prefix = str(params.get("right_prefix") or "")
    if prefix:
        right = right.rename(columns={column: f"{prefix}{column}" for column in right.columns if column != right_key})

    return dataframe.merge(right, how=join_type, left_on=left_key, right_on=right_key)


def _normalize_fields(
    dataframe: pd.DataFrame,
    params: dict[str, Any],
    flags_by_index: dict[Any, list[str]],
    flag_details_by_index: dict[Any, list[dict[str, Any]]],
    step_context: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    working = dataframe.copy()
    normalized_fields = 0
    invalid_values = 0
    for config in _normalization_configs(params):
        source = str(config.get("source") or config.get("field") or "")
        output = str(config.get("output") or config.get("target") or source)
        output_type = str(config.get("type") or "text")
        on_invalid = str(config.get("on_invalid") or "blank")
        invalid_flag = str(config.get("invalid_flag") or f"invalid_{output_type}_{output}")
        if not source or not output or source not in working.columns:
            continue

        original = working[source]
        normalized = original.apply(lambda value: _normalize_value(value, output_type))
        invalid_mask = original.apply(lambda value: normalize_text(value) is not None) & normalized.isna()

        if on_invalid == "keep_original":
            normalized = normalized.where(~invalid_mask, original)
        elif on_invalid == "flag":
            for index in original.index[invalid_mask]:
                raw_value = original.loc[index]
                _append_flag_detail(
                    flags_by_index,
                    flag_details_by_index,
                    index,
                    flag=invalid_flag,
                    step_context=step_context,
                    field=output,
                    source=source,
                    output=output,
                    raw_value=raw_value,
                    message=f"{source} value could not be converted to {output_type}.",
                    hint=_normalization_hint(output_type),
                )
            invalid_values += int(invalid_mask.sum())
        elif on_invalid == "stop_run" and bool(invalid_mask.any()):
            raise ValueError(f"Normalize fields could not convert {int(invalid_mask.sum())} value(s) in {source} to {output_type}.")

        working[output] = normalized
        normalized_fields += 1

    return working, {"fields": normalized_fields, "invalid_values": invalid_values}


def _append_flag_detail(
    flags_by_index: dict[Any, list[str]],
    flag_details_by_index: dict[Any, list[dict[str, Any]]],
    index: Any,
    *,
    flag: str,
    step_context: dict[str, Any],
    field: str,
    source: str,
    output: str,
    raw_value: object,
    message: str,
    hint: str,
    context: dict[str, Any] | None = None,
) -> None:
    flags_by_index.setdefault(index, []).append(flag)
    detail = {
        "flag": flag,
        "step_id": step_context.get("step_id"),
        "step_label": step_context.get("step_label"),
        "step_position": step_context.get("step_position"),
        "operation": step_context.get("operation"),
        "field": field,
        "source": source,
        "output": output,
        "raw_value": _detail_value(raw_value),
        "row_index": _detail_value(index),
        "message": message,
        "hint": hint,
    }
    if context:
        detail["context"] = context
    flag_details_by_index.setdefault(index, []).append(detail)


def _unique_flag_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for detail in details:
        key = json.dumps(detail, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(detail)
    return ordered


def _detail_value(value: object) -> object | None:
    if isinstance(value, dict):
        return {str(key): _detail_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_detail_value(item) for item in value]
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalization_hint(output_type: str) -> str:
    if output_type == "date":
        return "Use a supported date value or update this step's date parsing rule."
    if output_type == "boolean":
        return "Use a recognizable yes/no value or change this field's normalization type."
    if output_type == "number":
        return "Use a numeric value or change this field's normalization type."
    return "Update the source value or change this field's normalization rule."


def _normalization_configs(params: dict[str, Any]) -> list[dict[str, Any]]:
    shared = {
        "type": params.get("type") or "text",
        "on_invalid": params.get("on_invalid") or "blank",
        "invalid_flag": params.get("invalid_flag") or "",
    }
    configs: list[dict[str, Any]] = []

    fields = params.get("fields")
    if isinstance(fields, str):
        fields = [field.strip() for field in fields.split(",") if field.strip()]
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, str):
                configs.append({**shared, "source": field, "output": field})
            elif isinstance(field, dict):
                source = str(field.get("source") or field.get("field") or "")
                configs.append({**shared, **field, "output": field.get("output") or field.get("target") or source})

    mappings = params.get("mappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            source = str(mapping.get("source") or "")
            configs.append({**shared, **mapping, "output": mapping.get("output") or mapping.get("target") or source})

    return configs


def _normalize_value(value: object, output_type: str) -> object | None:
    if output_type == "text":
        return normalize_text(value)
    if output_type == "category":
        return normalize_category(value)
    if output_type == "boolean":
        return normalize_boolean(value)
    if output_type == "date":
        return parse_date(value)
    if output_type == "number":
        return safe_float(value)
    raise ValueError(f"Unsupported normalization output type: {output_type}")


def _load_data_file(paths: ProjectPaths, file_value: str) -> pd.DataFrame:
    candidate = paths.root / file_value
    if Path(file_value).is_absolute():
        candidate = Path(file_value)
    resolved = candidate.resolve()
    root = paths.root.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Join data file must be inside the GLADR workspace.")
    if not resolved.exists():
        raise FileNotFoundError(f"Join data file does not exist: {file_value}")

    if resolved.suffix.lower() == ".csv":
        return pd.read_csv(resolved)
    if resolved.suffix.lower() == ".json":
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            records = payload.get("records")
            if isinstance(records, list):
                return pd.DataFrame.from_records(records)
            return pd.DataFrame([payload])
        if isinstance(payload, list):
            return pd.DataFrame.from_records(payload)
    raise ValueError(f"Unsupported join data file type: {resolved.suffix}")


def _pivot_join_file(dataframe: pd.DataFrame, pivot: dict[str, Any]) -> pd.DataFrame:
    index = str(pivot.get("index") or "")
    columns = str(pivot.get("columns") or "")
    values = str(pivot.get("values") or "")
    prefix = str(pivot.get("prefix") or "")
    for field in (index, columns, values):
        if field not in dataframe.columns:
            raise ValueError(f"Pivot field is not in the join data file: {field}")

    wide = dataframe.pivot_table(index=index, columns=columns, values=values, aggfunc="first").reset_index()
    wide.columns = [
        index if column == index else f"{prefix}{column}"
        for column in wide.columns.astype(str)
    ]
    return wide


def _filter_mask(dataframe: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    masks: list[pd.Series] = []

    conditions = params.get("conditions")
    if isinstance(conditions, list):
        masks.extend(
            mask
            for condition in conditions
            if isinstance(condition, dict)
            for mask in [_condition_mask(dataframe, condition)]
            if mask is not None
        )

    required_field = str(params.get("required_field") or "")
    if required_field and required_field in dataframe.columns:
        masks.append(dataframe[required_field].apply(_is_blank))

    minimum_populated = params.get("minimum_populated_fields")
    if minimum_populated not in (None, ""):
        ignored = set(_fields({"fields": params.get("ignored_fields", [])}))
        minimum = int(minimum_populated)
        masks.append(dataframe.apply(lambda row: _populated_field_count(row, ignored) < minimum, axis=1))

    if not masks:
        return pd.Series([True] * len(dataframe), index=dataframe.index)

    match = str(params.get("match") or "all")
    combined = masks[0]
    for mask in masks[1:]:
        combined = combined | mask if match == "any" else combined & mask
    return combined


def _condition_mask(dataframe: pd.DataFrame, condition: dict[str, Any]) -> pd.Series | None:
    field = str(condition.get("field") or "")
    operator = str(condition.get("operator") or "equals")
    value = condition.get("value")
    if field not in dataframe.columns:
        return None

    series = dataframe[field]
    if operator == "is_missing":
        return series.apply(_is_blank)
    if operator == "is_not_missing":
        return ~series.apply(_is_blank)
    if operator == "equals":
        return series.apply(lambda item: _compare_text(item) == _compare_text(value))
    if operator == "not_equals":
        return series.apply(lambda item: _compare_text(item) != _compare_text(value))
    if operator == "contains":
        needle = str(_compare_text(value) or "").lower()
        return series.apply(lambda item: needle in str(_compare_text(item) or "").lower())
    if operator == "not_contains":
        needle = str(_compare_text(value) or "").lower()
        return series.apply(lambda item: needle not in str(_compare_text(item) or "").lower())
    if operator in {"gt", "gte", "lt", "lte"}:
        expected = safe_float(value)
        if expected is None:
            return pd.Series([False] * len(dataframe), index=dataframe.index)
        return series.apply(lambda item: _compare_numbers(safe_float(item), expected, operator))
    if operator in {"in", "not_in"}:
        values = value if isinstance(value, list) else str(value or "").split(",")
        normalized = {_compare_text(item) for item in values}
        mask = series.apply(lambda item: _compare_text(item) in normalized)
        return ~mask if operator == "not_in" else mask
    raise ValueError(f"Unsupported filter operator: {operator}")


def _populated_field_count(row: pd.Series, ignored_fields: set[str]) -> int:
    return sum(1 for field, value in row.items() if field not in ignored_fields and not _is_blank(value))


def _is_blank(value: object) -> bool:
    if isinstance(value, (dict, list, tuple, set)):
        return False
    return normalize_text(value) is None


def _compare_text(value: object) -> str | None:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True)
    return normalize_text(value)


def _compare_numbers(actual: float | None, expected: float, operator: str) -> bool:
    if actual is None:
        return False
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    return actual <= expected


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
    return "row filter"


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


def _math_result(row: pd.Series, params: dict[str, Any]) -> float | None:
    left = _math_operand(row, params, "left")
    right = _math_operand(row, params, "right")
    if left is None or right is None:
        return None

    operator = str(params.get("operator") or "divide")
    if operator == "add":
        result = left + right
    elif operator == "subtract":
        result = left - right
    elif operator == "multiply":
        result = left * right
    elif operator == "divide":
        if right == 0:
            return None
        result = left / right
    else:
        raise ValueError(f"Unsupported math operator: {operator}")

    precision = params.get("precision")
    if precision not in (None, ""):
        return round(result, int(precision))
    return result


def _math_operand(row: pd.Series, params: dict[str, Any], side: str) -> float | None:
    field = str(params.get(f"{side}_field") or params.get(side) or "")
    if field:
        return safe_float(row.get(field))
    return safe_float(params.get(f"{side}_value"))


def _fields(params: dict[str, Any]) -> list[str]:
    fields = params.get("fields", [])
    if isinstance(fields, str):
        return [field.strip() for field in fields.split(",") if field.strip()]
    if not isinstance(fields, list):
        return []
    return [str(field) for field in fields]


def _operation_label(operation: str) -> str:
    definition = next((item for item in OPERATION_LIBRARY if item["operation"] == operation), None)
    return str(definition["label"]) if definition else operation.replace("_", " ").title()


def _summarize_operation(
    operation: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    before_rows: int,
    after_rows: int,
) -> str:
    if operation == "remove_stub_rows":
        return f"Removed {metrics.get('stub_rows', 0)} stub row(s) from {before_rows} row(s)."
    if operation == "filter_rows":
        detail = metrics.get("filter_description") or _filter_description(params)
        return f"{detail} Retained {after_rows} of {before_rows} row(s)."
    if operation in {"custom_python", "static_code"}:
        return f"Ran allowlisted Python operation {params.get('function')}."
    if before_rows != after_rows:
        return f"Applied {operation.replace('_', ' ')} to {before_rows} row(s), retaining {after_rows}."
    return f"Applied {operation.replace('_', ' ')} to {after_rows} row(s)."


def _derive_recurrence_type(raw_value: object) -> str | None:
    text = normalize_text(raw_value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"residual", "progression"}:
        return lowered.title()
    if parse_date(text):
        return "Date"
    return normalize_category(text)

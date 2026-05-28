"""Adapter for the GBM main sheet CSV export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gladr.ingestion.adapters.base_adapter import AdapterRunResult, BaseAdapter
from gladr.ingestion.normalizers import (
    compute_age_years,
    normalize_category,
    normalize_text,
    parse_date,
    safe_float,
)
from gladr.ingestion.spec_engine import execute_ingestion_spec, load_default_spec


class GBMRegistryAdapter(BaseAdapter):
    adapter_id = "gbm_registry"
    source_glob = "data/raw/registry/main_sheet/*.csv"
    default_spec_id = "gbm_registry_default"

    column_map = {
        "Histo Report?": "histo_report",
        "Contributor": "contributor",
        "K-number": "patient_id",
        "DOB": "dob",
        "Sex": "sex",
        "Presentation Date": "presentation_date",
        "Age at presentation": "age_at_presentation",
        "Neutrophils (presentation)": "neutrophils",
        "Lymphocytes (presentation)": "lymphocytes",
        "First contrast MRI": "first_mri_date",
        "Side": "tumour_side",
        "Lobe": "tumour_lobe",
        "Peri-ventricular": "periventricular",
        "Multifocal": "multifocal",
        "Resection": "resection_date",
        "Post-op MRI Date": "postop_mri_date",
        "5-ALA": "five_ala",
        "Residual contrast enhancement": "residual_enhancement",
        "Radiotherapy": "radiotherapy",
        "TMZ": "tmz",
        "First recurrence evidence": "first_recurrence_evidence",
        "Recurrence side": "recurrence_side",
        "Recurrence lobe": "recurrence_lobe",
        "Local": "recurrence_local",
        "DOD": "dod",
        "Notes": "notes",
        "QMC Local": "qmc_local_raw"
    }

    def load_raw(self, source_path: Path) -> pd.DataFrame:
        return pd.read_csv(source_path)

    def default_spec(self) -> dict[str, Any]:
        return load_default_spec(self.adapter_id)

    def transform(
        self,
        dataframe: pd.DataFrame,
        source_path: Path,
        spec: dict[str, Any] | None = None,
        paths: Any | None = None,
    ) -> AdapterRunResult:
        return execute_ingestion_spec(self, dataframe, source_path, spec or self.default_spec(), paths=paths)

    def custom_operation_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "function": "gbm_registry.normalize_histo_report",
                "label": "Normalize histology report status",
                "description": "Converts '?' to Unknown and applies GBM-specific histology status cleanup.",
                "inputs": ["histo_report"],
                "outputs": ["histo_report"],
            },
            {
                "function": "gbm_registry.split_qmc_local",
                "label": "Split QMC local field",
                "description": "Splits QMC Local into a boolean local flag and referring centre text.",
                "inputs": ["qmc_local_raw"],
                "outputs": ["qmc_local", "referring_centre"],
            },
            {
                "function": "gbm_registry.derive_resection_type",
                "label": "Derive resection type",
                "description": "Classifies a row from the presence or absence of a resection date.",
                "inputs": ["resection_date"],
                "outputs": ["resection_type"],
            },
            {
                "function": "gbm_registry.derive_recurrence_type",
                "label": "Derive recurrence type",
                "description": "Classifies recurrence evidence as residual, progression, date, or category text.",
                "inputs": ["first_recurrence_evidence"],
                "outputs": ["recurrence_type"],
            },
        ]

    def apply_custom_operation(
        self,
        function_id: str,
        dataframe: pd.DataFrame,
        params: dict[str, Any],
    ) -> pd.DataFrame:
        working = dataframe.copy()
        if function_id == "gbm_registry.normalize_histo_report":
            field = str((params.get("inputs") or ["histo_report"])[0])
            output = str((params.get("outputs") or [field])[0])
            if field in working.columns:
                working[output] = working[field].apply(self._normalize_histo_report)
            return working

        if function_id == "gbm_registry.split_qmc_local":
            field = str((params.get("inputs") or ["qmc_local_raw"])[0])
            outputs = params.get("outputs") or ["qmc_local", "referring_centre"]
            qmc_output = str(outputs[0])
            centre_output = str(outputs[1])
            if field in working.columns:
                split_values = working[field].apply(self._split_qmc_local)
                working[qmc_output] = split_values.apply(lambda value: value[0])
                working[centre_output] = split_values.apply(lambda value: value[1])
            return working

        if function_id == "gbm_registry.derive_resection_type":
            field = str((params.get("inputs") or ["resection_date"])[0])
            output = str((params.get("outputs") or ["resection_type"])[0])
            if field in working.columns:
                working[output] = working[field].apply(self._derive_resection_type)
            return working

        if function_id == "gbm_registry.derive_recurrence_type":
            field = str((params.get("inputs") or ["first_recurrence_evidence"])[0])
            output = str((params.get("outputs") or ["recurrence_type"])[0])
            if field in working.columns:
                working[output] = working[field].apply(self._derive_recurrence_type)
            return working

        return super().apply_custom_operation(function_id, dataframe, params)

    @staticmethod
    def _resolve_age(raw_age: object, dob: str | None, presentation_date: str | None) -> int | None:
        value = safe_float(raw_age)
        if value is not None:
            return int(value)
        return compute_age_years(dob, presentation_date)

    @staticmethod
    def _derive_resection_type(resection_date: str | None) -> str:
        return "Resection" if resection_date else "Biopsy/None"

    @staticmethod
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

    @staticmethod
    def _normalize_histo_report(value: object) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, str) and value.strip() == "?":
            return "Unknown"
        text = normalize_text(value)
        if text is None:
            return None
        return text

    @staticmethod
    def _split_qmc_local(value: object) -> tuple[bool | None, str | None]:
        text = normalize_text(value)
        if text is None:
            return None, None

        lowered = text.lower()
        if lowered in {"yes", "qmc", "local"}:
            return True, "QMC"
        if lowered in {"no", "non-local", "non local"}:
            return False, None
        if "qmc" in lowered:
            return True, text
        return False, text

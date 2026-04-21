"""Adapter for the GBM main sheet CSV export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gladr.contracts import canonical_field_names, load_contract
from gladr.ingest.adapters.base_adapter import AdapterRunResult, BaseAdapter
from gladr.ingest.normalizers import (
    compute_age_years,
    compute_nlr,
    normalize_boolean,
    normalize_category,
    normalize_text,
    parse_date,
    safe_float,
)
from gladr.ingest.quality_flags import unique_flags
from gladr.ingest.validators import is_stub_row, validate_required_columns


LOBE_MAPPING = load_contract("lobe_mapping.json")


class GBMRegistryAdapter(BaseAdapter):
    adapter_id = "gbm_registry"
    source_glob = "data/raw/main_sheet/*.csv"

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

    def transform(self, dataframe: pd.DataFrame, source_path: Path) -> AdapterRunResult:
        if "K-number" not in dataframe.columns and "k-number" in dataframe.columns:
            dataframe = dataframe.rename(columns={"k-number": "K-number"})
        validate_required_columns(dataframe, ["K-number"])

        raw_rows = len(dataframe)
        stub_mask = dataframe.apply(is_stub_row, axis=1, id_column="K-number")
        stub_rows = int(stub_mask.sum())
        working = dataframe.loc[~stub_mask].copy()
        working = working.rename(columns={old: new for old, new in self.column_map.items() if old in working.columns})

        records: list[dict[str, object]] = []
        report: list[dict[str, object]] = []

        for _, row in working.iterrows():
            patient_id = normalize_text(row.get("patient_id"))
            flags: list[str] = []

            dob = parse_date(row.get("dob"))
            if normalize_text(row.get("dob")) is not None and dob is None:
                flags.append("invalid_dob")

            presentation_date = parse_date(row.get("presentation_date"))
            if normalize_text(row.get("presentation_date")) is not None and presentation_date is None:
                flags.append("invalid_presentation_date")

            first_mri_date = parse_date(row.get("first_mri_date"))
            resection_date = parse_date(row.get("resection_date"))
            postop_mri_date = parse_date(row.get("postop_mri_date"))
            dod = parse_date(row.get("dod"))
            recurrence_date = parse_date(row.get("first_recurrence_evidence"))

            neutrophils = safe_float(row.get("neutrophils"))
            lymphocytes = safe_float(row.get("lymphocytes"))

            tumour_lobe = normalize_category(row.get("tumour_lobe"))
            if tumour_lobe:
                tumour_lobe = LOBE_MAPPING.get(tumour_lobe.lower(), tumour_lobe)

            recurrence_lobe = normalize_category(row.get("recurrence_lobe"))
            if recurrence_lobe:
                recurrence_lobe = LOBE_MAPPING.get(recurrence_lobe.lower(), recurrence_lobe)

            first_recurrence_raw = normalize_text(row.get("first_recurrence_evidence"))
            qmc_local, referring_centre = self._split_qmc_local(row.get("qmc_local_raw"))
            age_at_presentation = self._resolve_age(row.get("age_at_presentation"), dob, presentation_date)

            if age_at_presentation is None:
                flags.append("missing_age_at_presentation")

            record = {
                "patient_id": patient_id,
                "source": self.adapter_id,
                "contributor": normalize_category(row.get("contributor")),
                "dob": dob,
                "sex": normalize_category(row.get("sex")),
                "presentation_date": presentation_date,
                "age_at_presentation": age_at_presentation,
                "neutrophils": neutrophils,
                "lymphocytes": lymphocytes,
                "nlr": compute_nlr(neutrophils, lymphocytes),
                "first_mri_date": first_mri_date,
                "tumour_side": normalize_category(row.get("tumour_side")),
                "tumour_lobe": tumour_lobe,
                "periventricular": normalize_boolean(row.get("periventricular")),
                "multifocal": normalize_boolean(row.get("multifocal")),
                "resection_date": resection_date,
                "resection_type": self._derive_resection_type(resection_date),
                "postop_mri_date": postop_mri_date,
                "five_ala": normalize_boolean(row.get("five_ala")),
                "residual_enhancement": normalize_text(row.get("residual_enhancement")),
                "radiotherapy": normalize_boolean(row.get("radiotherapy")),
                "tmz": normalize_text(row.get("tmz")),
                "recurrence_date": recurrence_date,
                "recurrence_type": self._derive_recurrence_type(first_recurrence_raw),
                "recurrence_side": normalize_category(row.get("recurrence_side")),
                "recurrence_lobe": recurrence_lobe,
                "recurrence_local": normalize_boolean(row.get("recurrence_local")),
                "dod": dod,
                "qmc_local": qmc_local,
                "referring_centre": referring_centre,
                "histo_report": self._normalize_histo_report(row.get("histo_report")),
                "notes": normalize_text(row.get("notes")),
                "data_quality_flags": []
            }

            record["data_quality_flags"] = unique_flags(flags)
            records.append(record)
            report.append(
                {
                    "patient_id": patient_id,
                    "source_file": source_path.name,
                    "flags": record["data_quality_flags"]
                }
            )

        normalized = pd.DataFrame.from_records(records)
        for field in canonical_field_names():
            if field not in normalized.columns:
                normalized[field] = None
        normalized = normalized[canonical_field_names()]

        return AdapterRunResult(
            dataframe=normalized,
            ingestion_report=report,
            source_summary={
                "adapter": self.adapter_id,
                "file": source_path.name,
                "rows_raw": raw_rows,
                "rows_stub": stub_rows,
                "rows_ingested": len(normalized)
            },
        )

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
    def _derive_recurrence_type(raw_value: str | None) -> str | None:
        if raw_value is None:
            return None
        lowered = raw_value.lower()
        if lowered in {"residual", "progression"}:
            return lowered.title()
        if parse_date(raw_value):
            return "Date"
        return normalize_category(raw_value)

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

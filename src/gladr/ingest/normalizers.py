"""Normalization helpers used by ingestion adapters."""

from __future__ import annotations

from datetime import datetime

import pandas as pd


NULL_TOKENS = {
    "",
    "?",
    "na",
    "n/a",
    "nd",
    "not documented",
    "none",
    "null",
    "nan",
}

TRUE_TOKENS = {"yes", "y", "true", "1"}
FALSE_TOKENS = {"no", "n", "false", "0"}


def normalize_missing(value: object) -> object | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str) and value.strip().lower() in NULL_TOKENS:
        return None
    return value


def normalize_text(value: object) -> str | None:
    normalized = normalize_missing(value)
    if normalized is None:
        return None
    return str(normalized).strip()


def normalize_category(value: object) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    return normalized.title()


def normalize_boolean(value: object) -> bool | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered in TRUE_TOKENS:
        return True
    if lowered in FALSE_TOKENS:
        return False
    return None


def parse_date(value: object) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            continue

    parsed = pd.to_datetime(normalized, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def safe_float(value: object) -> float | None:
    normalized = normalize_missing(value)
    if normalized is None:
        return None

    converted = pd.to_numeric(pd.Series([normalized]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    return float(converted)


def compute_age_years(dob: str | None, presentation_date: str | None) -> int | None:
    if not dob or not presentation_date:
        return None

    dob_dt = datetime.fromisoformat(dob)
    presentation_dt = datetime.fromisoformat(presentation_date)
    return int((presentation_dt - dob_dt).days // 365.25)


def compute_nlr(neutrophils: float | None, lymphocytes: float | None) -> float | None:
    if neutrophils is None or lymphocytes in (None, 0):
        return None
    return round(neutrophils / lymphocytes, 3)

"""Validation helpers used during ingestion."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def validate_required_columns(dataframe: pd.DataFrame, required_columns: Iterable[str]) -> None:
    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        raise KeyError(f"Missing required columns: {', '.join(sorted(missing))}")


def is_stub_row(row: pd.Series, id_column: str) -> bool:
    if pd.isna(row.get(id_column)):
        return True

    remaining = row.drop(labels=[id_column], errors="ignore")
    return remaining.fillna("").astype(str).str.strip().eq("").all()

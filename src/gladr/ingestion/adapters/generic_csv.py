"""Generic CSV adapter for workbench-configured imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gladr.ingestion.adapters.base_adapter import AdapterRunResult, BaseAdapter
from gladr.ingestion.spec_engine import execute_ingestion_spec, load_default_spec


class GenericCSVAdapter(BaseAdapter):
    adapter_id = "generic_csv"
    source_glob = "data/raw/imports/*.csv"
    default_spec_id = "generic_csv_default"
    publish_without_matches = True

    def match_files(self, project_root: Path) -> list[Path]:
        patterns = [
            "data/raw/imports/*.csv",
            "data/raw/uploads/*.csv",
            "data/raw/*.csv",
        ]
        files = {
            path.resolve(): path
            for pattern in patterns
            for path in project_root.glob(pattern)
        }
        return sorted(files.values())

    def load_raw(self, source_path: Path) -> pd.DataFrame:
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return pd.read_csv(
                    source_path,
                    sep=None,
                    engine="python",
                    dtype=object,
                    keep_default_na=False,
                    encoding=encoding,
                )
            except UnicodeDecodeError as error:
                last_error = error
        if last_error:
            raise last_error
        raise ValueError(f"Could not read CSV file: {source_path}")

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

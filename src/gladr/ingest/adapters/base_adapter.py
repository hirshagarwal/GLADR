"""Base adapter interface for raw data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class AdapterRunResult:
    dataframe: pd.DataFrame
    ingestion_report: list[dict[str, object]]
    source_summary: dict[str, object]


class BaseAdapter(ABC):
    adapter_id: str = ""
    source_glob: str = ""

    def match_files(self, project_root: Path) -> list[Path]:
        return sorted(project_root.glob(self.source_glob))

    @abstractmethod
    def load_raw(self, source_path: Path) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def transform(self, dataframe: pd.DataFrame, source_path: Path) -> AdapterRunResult:
        raise NotImplementedError

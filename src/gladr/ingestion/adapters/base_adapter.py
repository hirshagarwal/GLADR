"""Base adapter interface for raw data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class IngestionStep:
    step_id: str
    label: str
    summary: str
    status: str = "completed"
    execution_mode: str = "static_code"
    source_file: str | None = None
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "summary": self.summary,
            "status": self.status,
            "execution_mode": self.execution_mode,
            "source_file": self.source_file,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metrics": self.metrics,
        }


@dataclass
class AdapterRunResult:
    dataframe: pd.DataFrame
    ingestion_report: list[dict[str, object]]
    source_summary: dict[str, object]
    steps: list[IngestionStep | dict[str, object]] = field(default_factory=list)


class BaseAdapter(ABC):
    adapter_id: str = ""
    source_glob: str = ""
    default_spec_id: str | None = None
    publish_without_matches: bool = False

    def match_files(self, project_root: Path) -> list[Path]:
        return sorted(project_root.glob(self.source_glob))

    def default_spec(self) -> dict[str, Any] | None:
        return None

    def custom_operation_definitions(self) -> list[dict[str, Any]]:
        return []

    def apply_custom_operation(
        self,
        function_id: str,
        dataframe: pd.DataFrame,
        params: dict[str, Any],
    ) -> pd.DataFrame:
        raise ValueError(f"Adapter {self.adapter_id} does not allow custom operation {function_id}.")

    @abstractmethod
    def load_raw(self, source_path: Path) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def transform(
        self,
        dataframe: pd.DataFrame,
        source_path: Path,
        spec: dict[str, Any] | None = None,
        paths: Any | None = None,
    ) -> AdapterRunResult:
        raise NotImplementedError

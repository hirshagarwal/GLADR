"""Base class for analysis scripts."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from gladr.core.run_context import RunContext


class BaseAnalysisScript(ABC):
    script_id: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    priority: int = 99

    @abstractmethod
    def build(self, dataframe: pd.DataFrame, run_context: RunContext, manifest_run_id: str) -> dict[str, object]:
        raise NotImplementedError

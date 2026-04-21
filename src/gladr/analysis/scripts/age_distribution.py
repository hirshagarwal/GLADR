"""Age distribution analysis."""

from __future__ import annotations

import pandas as pd

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.core.run_context import RunContext


class AgeDistributionScript(BaseAnalysisScript):
    script_id = "age_distribution"
    title = "Age at Presentation"
    description = "Histogram-ready distribution of age at presentation."
    category = "Demographics"
    priority = 2

    def build(self, dataframe: pd.DataFrame, run_context: RunContext, manifest_run_id: str) -> dict[str, object]:
        values = [int(value) for value in dataframe["age_at_presentation"].dropna().tolist()]
        return {
            "script_id": self.script_id,
            "run_id": run_context.run_id,
            "manifest_run_id": manifest_run_id,
            "run_datetime": run_context.run_datetime,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "metadata": {
                "n": len(values),
                "exclusions": f"Excluded {len(dataframe) - len(values)} rows with missing age.",
                "notes": "Histogram scaffold output."
            },
            "visualization": {
                "type": "histogram",
                "library": "generic",
                "config": {
                    "x_field": "values",
                    "x_label": "Age at Presentation (years)",
                    "bin_count": 12,
                    "overlay_normal": False
                }
            },
            "data": {"values": values},
        }

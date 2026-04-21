"""Sex breakdown analysis."""

from __future__ import annotations

import pandas as pd

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.core.run_context import RunContext


class SexBreakdownScript(BaseAnalysisScript):
    script_id = "sex_breakdown"
    title = "Sex Distribution"
    description = "Counts by sex for the currently ingested cohort."
    category = "Demographics"
    priority = 3

    def build(self, dataframe: pd.DataFrame, run_context: RunContext, manifest_run_id: str) -> dict[str, object]:
        counts = (
            dataframe["sex"]
            .fillna("Unknown")
            .astype(str)
            .value_counts()
            .rename_axis("sex")
            .reset_index(name="count")
            .to_dict(orient="records")
        )

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
                "n": int(len(dataframe)),
                "exclusions": "",
                "notes": "Bar chart scaffold output."
            },
            "visualization": {
                "type": "bar",
                "library": "generic",
                "config": {
                    "x_field": "sex",
                    "y_field": "count",
                    "x_label": "Sex",
                    "y_label": "Patients",
                    "orientation": "vertical",
                    "sort_by": "count"
                }
            },
            "data": {"rows": counts},
        }

"""Baseline cohort summary analysis."""

from __future__ import annotations

import pandas as pd

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.core.run_context import RunContext


class CohortSummaryScript(BaseAnalysisScript):
    script_id = "cohort_summary"
    title = "Cohort Demographics"
    description = "Initial cohort-level summary cards and a contributor table."
    category = "Demographics"
    priority = 1

    def build(self, dataframe: pd.DataFrame, run_context: RunContext, manifest_run_id: str) -> dict[str, object]:
        sex_series = dataframe["sex"].dropna().astype(str)
        contributor_rows = (
            dataframe["contributor"]
            .fillna("Unknown")
            .value_counts()
            .rename_axis("contributor")
            .reset_index(name="count")
            .to_dict(orient="records")
        )

        median_age = dataframe["age_at_presentation"].dropna().median()
        pct_male = None
        if not sex_series.empty:
            pct_male = round(float((sex_series.str.lower() == "m").mean() * 100), 1)

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
                "notes": "Baseline scaffold output."
            },
            "visualization": {
                "type": "multi",
                "library": "generic",
                "panels": [
                    {
                        "type": "scalar_cards",
                        "config": {
                            "cards": [
                                {"label": "Total Patients", "value_field": "total_patients", "format": "int"},
                                {"label": "Median Age", "value_field": "median_age", "unit": "years", "format": "float1"},
                                {"label": "Pct Male", "value_field": "pct_male", "unit": "%", "format": "float1"}
                            ]
                        }
                    },
                    {
                        "type": "table",
                        "config": {
                            "columns": [
                                {"field": "contributor", "label": "Contributor", "format": "string"},
                                {"field": "count", "label": "Patients", "format": "int"}
                            ]
                        }
                    }
                ]
            },
            "data": {
                "total_patients": int(len(dataframe)),
                "median_age": round(float(median_age), 1) if pd.notna(median_age) else None,
                "pct_male": pct_male,
                "contributor_rows": contributor_rows
            },
        }

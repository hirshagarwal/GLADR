from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.core.paths import ProjectPaths
from gladr.dashboard.manifest_loader import load_dashboard_payload


class DashboardManifestLoaderTests(unittest.TestCase):
    def test_discovers_all_analysis_artifacts_and_pipeline_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = _project_paths(Path(directory))
            paths.ensure_runtime_dirs()

            _write_json(
                paths.canonical_manifests_outputs_dir / "manifest_20260419_100000.json",
                {
                    "run_id": "20260419_100000",
                    "pipeline_version": "0.1.0",
                    "run_datetime": "2026-04-19T10:00:00-04:00",
                    "sources": [{"adapter": "demo", "file": "demo.csv", "rows_raw": 6, "rows_stub": 1, "rows_ingested": 4}],
                    "summary": {"source_files": 1, "raw_rows": 6, "stub_rows": 1, "ingested_rows": 4},
                    "steps": [
                        {
                            "step_id": "demo:filter_sparse",
                            "label": "Filter sparse rows",
                            "summary": "Removed sparse source rows.",
                            "status": "completed",
                            "execution_mode": "static_code",
                            "inputs": ["demo.csv"],
                            "outputs": ["clean_dataset"],
                            "metrics": {"operation": "filter_rows", "filtered_rows": 1, "remaining_rows": 5},
                        },
                        {
                            "step_id": "demo:filter_analysis_ready",
                            "label": "Filter analysis-ready rows",
                            "summary": "Removed rows outside the analysis-ready registry cohort.",
                            "status": "completed",
                            "execution_mode": "static_code",
                            "inputs": ["demo.csv"],
                            "outputs": ["clean_dataset"],
                            "metrics": {"operation": "filter_rows", "filtered_rows": 1, "remaining_rows": 4},
                        }
                    ],
                    "specs": [
                        {
                            "source_file": "demo.csv",
                            "spec": {
                                "steps": [
                                    {
                                        "id": "filter_sparse",
                                        "operation": "filter_rows",
                                        "label": "Filter sparse rows",
                                        "params": {"action": "drop", "match": "all", "conditions": [], "minimum_populated_fields": 2},
                                    },
                                    {
                                        "id": "filter_analysis_ready",
                                        "operation": "filter_rows",
                                        "label": "Filter analysis-ready rows",
                                        "params": {
                                            "action": "drop",
                                            "match": "all",
                                            "conditions": [{"field": "IDH1/2", "operator": "is_missing"}],
                                        },
                                    },
                                ]
                            },
                        }
                    ],
                    "total_rows": 4,
                    "canonical_schema_version": "1.0.0",
                },
            )
            _write_json(
                paths.canonical_ingestion_outputs_dir / "latest.json",
                {"manifest": "manifests/manifest_20260419_100000.json"},
            )
            _write_json(
                paths.analysis_outputs_dir / "latest.json",
                {
                    "cohort_summary": "artifacts/cohort_summary_20260419_100500.json",
                    "age_distribution": "artifacts/age_distribution_20260419_100600.json",
                },
            )
            _write_json(
                paths.analysis_artifacts_outputs_dir / "cohort_summary_20260419_100500.json",
                _analysis_payload("cohort_summary", "Cohort", "20260419_100500", "20260419_100000", "2026-04-19T10:05:00-04:00", 4),
            )
            _write_json(
                paths.analysis_artifacts_outputs_dir / "age_distribution_20260419_100600.json",
                _analysis_payload(
                    "multivariable_logistic_regression",
                    "Model",
                    "20260419_100600",
                    "20260419_100000",
                    "2026-04-19T10:06:00-04:00",
                    2,
                    cohort_display="shared_model_frame",
                    cohort={
                        "display": "shared_model_frame",
                        "basis": "complete_case",
                        "input_rows": 4,
                        "included_rows": 2,
                        "excluded_rows": 2,
                        "required_fields": ["outcome", "predictor"],
                        "rules": [
                            {
                                "rule": "missing_required_model_field",
                                "count": 2,
                                "description": "Rows require complete outcome and selected predictor values.",
                            }
                        ],
                    },
                ),
            )

            payload = load_dashboard_payload(paths)

            self.assertEqual(payload["summary"]["ingestion_runs"], 1)
            self.assertEqual(payload["summary"]["analysis_artifacts"], 2)
            self.assertEqual(payload["summary"]["visualizations"], 2)
            self.assertEqual({item["script_id"] for item in payload["analyses"]}, {"cohort_summary", "multivariable_logistic_regression"})
            self.assertEqual([item["script_id"] for item in payload["analyses"]], ["multivariable_logistic_regression", "cohort_summary"])
            self.assertEqual(len(payload["pipeline"]), 1)
            self.assertEqual(len(payload["pipeline"][0]["stats_runs"]), 2)
            self.assertEqual(len(payload["pipeline"][0]["visualizations"]), 2)
            self.assertEqual([stage["id"] for stage in payload["stage_summaries"]], ["ingestion", "analysis", "visualization"])
            self.assertEqual(payload["stage_summaries"][0]["status"], "completed")
            ingestion_flow = payload["stage_summaries"][0]["current"]["flow"]
            self.assertEqual(ingestion_flow["steps"][0]["label"], "Filter sparse rows")
            self.assertEqual(ingestion_flow["steps"][0]["detail"], "Removed sparse source rows.")
            self.assertEqual(ingestion_flow["steps"][0]["execution_mode"], "static_code")
            self.assertEqual(payload["stage_summaries"][1]["current"]["metrics"][0]["value"], 1)
            self.assertEqual(payload["stage_summaries"][2]["current"]["metrics"][0]["value"], 1)
            self.assertEqual(len(payload["stage_summaries"][1]["current"]["metrics"]), 2)
            self.assertEqual(len(payload["stage_summaries"][2]["current"]["metrics"]), 2)
            model = payload["analyses"][0]
            self.assertEqual(model["cohort_display"], "shared_model_frame")
            self.assertEqual(model["cohort_trace"]["ingestion"]["raw_rows"], 6)
            self.assertEqual(model["cohort_trace"]["ingestion"]["clean_rows"], 4)
            self.assertEqual(model["cohort_trace"]["ingestion"]["rules"][0]["label"], "Filter sparse rows (sparse rows)")
            self.assertEqual(model["cohort_trace"]["ingestion"]["rules"][0]["conditions"], ["fewer than 2 populated field(s)"])
            self.assertEqual(model["cohort_trace"]["ingestion"]["rules"][1]["label"], "Filter analysis-ready rows (IDH1/2)")
            self.assertEqual(model["cohort_trace"]["ingestion"]["rules"][1]["conditions"], ["IDH1/2 is missing"])
            self.assertEqual(model["cohort_trace"]["analysis"]["included_rows"], 2)
            self.assertEqual(model["cohort_trace"]["analysis"]["excluded_rows"], 2)
            self.assertEqual(model["cohort_trace"]["analysis"]["required_fields"], ["outcome", "predictor"])


def _project_paths(root: Path) -> ProjectPaths:
    return ProjectPaths.from_root(root)


def _analysis_payload(
    script_id: str,
    title: str,
    run_id: str,
    manifest_run_id: str,
    run_datetime: str,
    n: int,
    *,
    cohort_display: str = "none",
    cohort: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "script_id": script_id,
        "run_id": run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": run_datetime,
        "title": title,
        "description": "Demo analysis",
        "category": "Demo",
        "priority": 1,
        "metadata": {"n": n},
        "visualization": {"type": "bar"},
        "data": {"rows": [{"label": "A", "value": 4}]},
    }
    if cohort_display:
        payload["cohort_display"] = cohort_display
    if cohort:
        payload["cohort"] = cohort
    return payload


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)


if __name__ == "__main__":
    unittest.main()

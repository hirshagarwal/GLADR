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
                paths.registry_manifests_outputs_dir / "manifest_20260419_100000.json",
                {
                    "run_id": "20260419_100000",
                    "pipeline_version": "0.1.0",
                    "run_datetime": "2026-04-19T10:00:00-04:00",
                    "sources": [{"adapter": "demo", "file": "demo.csv", "rows_ingested": 4}],
                    "summary": {"source_files": 1, "raw_rows": 4, "ingested_rows": 4},
                    "steps": [
                        {
                            "step_id": "demo_step",
                            "label": "Demo manifest step",
                            "summary": "This step came from the manifest.",
                            "status": "completed",
                            "execution_mode": "static_code",
                            "inputs": ["demo.csv"],
                            "outputs": ["clean_dataset"],
                            "metrics": {"rows": 4},
                        }
                    ],
                    "total_rows": 4,
                    "canonical_schema_version": "1.0.0",
                },
            )
            _write_json(
                paths.registry_ingestion_outputs_dir / "latest.json",
                {"manifest": "manifests/manifest_20260419_100000.json"},
            )
            _write_json(
                paths.analysis_outputs_dir / "latest.json",
                {"cohort_summary": "artifacts/cohort_summary_20260419_100500.json"},
            )
            _write_json(
                paths.analysis_artifacts_outputs_dir / "cohort_summary_20260419_100500.json",
                _analysis_payload("cohort_summary", "Cohort", "20260419_100500", "20260419_100000"),
            )
            _write_json(
                paths.analysis_artifacts_outputs_dir / "age_distribution_20260419_100600.json",
                _analysis_payload("age_distribution", "Age", "20260419_100600", "20260419_100000"),
            )

            payload = load_dashboard_payload(paths)

            self.assertEqual(payload["summary"]["ingestion_runs"], 1)
            self.assertEqual(payload["summary"]["analysis_artifacts"], 2)
            self.assertEqual(payload["summary"]["visualizations"], 2)
            self.assertEqual({item["script_id"] for item in payload["analyses"]}, {"cohort_summary", "age_distribution"})
            self.assertEqual(len(payload["pipeline"]), 1)
            self.assertEqual(len(payload["pipeline"][0]["stats_runs"]), 2)
            self.assertEqual(len(payload["pipeline"][0]["visualizations"]), 2)
            self.assertEqual([stage["id"] for stage in payload["stage_summaries"]], ["ingestion", "stats", "visualization"])
            self.assertEqual(payload["stage_summaries"][0]["status"], "completed")
            ingestion_flow = payload["stage_summaries"][0]["current"]["flow"]
            self.assertEqual(ingestion_flow["steps"][0]["label"], "Demo manifest step")
            self.assertEqual(ingestion_flow["steps"][0]["detail"], "This step came from the manifest.")
            self.assertEqual(ingestion_flow["steps"][0]["execution_mode"], "static_code")
            self.assertEqual(payload["stage_summaries"][1]["current"]["metrics"][0]["value"], 1)
            self.assertEqual(payload["stage_summaries"][2]["current"]["metrics"][0]["value"], 1)


def _project_paths(root: Path) -> ProjectPaths:
    return ProjectPaths.from_root(root)


def _analysis_payload(script_id: str, title: str, run_id: str, manifest_run_id: str) -> dict[str, object]:
    return {
        "script_id": script_id,
        "run_id": run_id,
        "manifest_run_id": manifest_run_id,
        "run_datetime": "2026-04-19T10:05:00-04:00",
        "title": title,
        "description": "Demo analysis",
        "category": "Demo",
        "priority": 1,
        "metadata": {"n": 4},
        "visualization": {"type": "bar"},
        "data": {"rows": [{"label": "A", "value": 4}]},
    }


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)


if __name__ == "__main__":
    unittest.main()

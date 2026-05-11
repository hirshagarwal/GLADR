from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.analysis.profiling import build_dataset_profile
from gladr.analysis.templates import build_cox_regression, build_univariate_auc_screen, list_analysis_templates
from gladr.core.paths import ProjectPaths
from gladr.core.run_context import RunContext


class AnalysisTemplateTests(unittest.TestCase):
    def test_profiles_latest_clean_dataset_variables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = ProjectPaths.from_root(Path(directory))
            paths.ensure_runtime_dirs()
            _write_latest_clean_dataset(paths)

            profile = build_dataset_profile(paths)

            self.assertEqual(profile["dataset"]["rows"], 4)
            variables = {variable["name"]: variable for variable in profile["variables"]}
            self.assertEqual(variables["recurrence"]["type"], "binary")
            self.assertEqual(variables["age_at_presentation"]["type"], "numeric")
            self.assertEqual(variables["tumour_lobe"]["type"], "categorical")

    def test_univariate_auc_screen_builds_ranked_models(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": True, "nlr": 5.0, "tumour_lobe": "Frontal"},
                {"recurrence": True, "nlr": 4.0, "tumour_lobe": "Frontal"},
                {"recurrence": False, "nlr": 1.2, "tumour_lobe": "Temporal"},
                {"recurrence": False, "nlr": 1.5, "tumour_lobe": "Temporal"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_univariate_auc_screen(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "tumour_lobe"]},
        )

        self.assertEqual(artifact["script_id"], "univariate_auc_screen")
        self.assertEqual(artifact["metadata"]["fit_count"], 2)
        self.assertEqual(artifact["data"]["rows"][0]["auc"], 1.0)
        self.assertTrue(artifact["data"]["roc_curves"])

    def test_lists_cox_regression_template(self) -> None:
        templates = {template["template_id"]: template for template in list_analysis_templates()}

        self.assertIn("cox_regression", templates)
        self.assertEqual(templates["cox_regression"]["category"], "Survival Modeling")
        self.assertEqual(
            [parameter["name"] for parameter in templates["cox_regression"]["parameters"]],
            ["start_date", "event_date", "censor_date", "predictors"],
        )

    def test_cox_regression_builds_hazard_ratios(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"resection_date": "2024-01-01", "recurrence_date": "2024-02-01", "dod": "2024-08-01", "nlr": 8.0, "sex": "M"},
                {"resection_date": "2024-01-01", "recurrence_date": "2024-03-01", "dod": "2024-08-01", "nlr": 7.0, "sex": "M"},
                {"resection_date": "2024-01-01", "recurrence_date": "2024-05-01", "dod": "2024-08-01", "nlr": 3.0, "sex": "F"},
                {"resection_date": "2024-01-01", "recurrence_date": None, "dod": "2024-08-01", "nlr": 2.0, "sex": "F"},
                {"resection_date": "2024-01-01", "recurrence_date": None, "dod": "2024-09-01", "nlr": 1.5, "sex": "F"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_cox_regression(
            dataframe,
            run_context,
            "manifest_1",
            {
                "start_date": "resection_date",
                "event_date": "recurrence_date",
                "censor_date": "dod",
                "predictors": ["nlr", "sex"],
            },
        )

        self.assertEqual(artifact["script_id"], "cox_regression")
        self.assertEqual(artifact["metadata"]["events"], 3)
        self.assertEqual(artifact["metadata"]["censored"], 2)
        self.assertGreaterEqual(len(artifact["data"]["rows"]), 2)
        self.assertTrue(all("hazard_ratio" in row for row in artifact["data"]["rows"]))
        self.assertTrue(all("p_value" in row for row in artifact["data"]["rows"]))


def _write_latest_clean_dataset(paths: ProjectPaths) -> None:
    manifest = {
        "run_id": "20260510_120000",
        "run_datetime": "2026-05-10T12:00:00-04:00",
    }
    dataset = {
        "records": [
            {"patient_id": "A", "recurrence": True, "age_at_presentation": 61, "tumour_lobe": "Frontal"},
            {"patient_id": "B", "recurrence": False, "age_at_presentation": 55, "tumour_lobe": "Temporal"},
            {"patient_id": "C", "recurrence": True, "age_at_presentation": 70, "tumour_lobe": "Frontal"},
            {"patient_id": "D", "recurrence": False, "age_at_presentation": None, "tumour_lobe": "Parietal"},
        ]
    }
    (paths.registry_datasets_outputs_dir / "clean_dataset_20260510_120000.json").write_text(
        json.dumps(dataset),
        encoding="utf-8",
    )
    (paths.registry_manifests_outputs_dir / "manifest_20260510_120000.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (paths.registry_ingestion_outputs_dir / "latest.json").write_text(
        json.dumps({
            "clean_dataset": "datasets/clean_dataset_20260510_120000.json",
            "manifest": "manifests/manifest_20260510_120000.json",
        }),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()

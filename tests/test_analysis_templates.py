from __future__ import annotations

import json
import math
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
from gladr.analysis.templates import (
    build_bootstrapped_multivariable_logistic_regression,
    build_cox_regression,
    build_hosmer_lemeshow_calibration,
    build_lasso_logistic_regression,
    build_multivariable_logistic_regression,
    build_univariate_auc_screen,
    list_analysis_templates,
)
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
            self.assertEqual(variables["residual_enhancement"]["type"], "binary")
            self.assertEqual(variables["age_at_presentation"]["type"], "numeric")
            self.assertEqual(variables["tumour_lobe"]["type"], "categorical")
            self.assertEqual(variables["age_at_presentation"]["present_rows"], [0, 1, 2])
            self.assertEqual(variables["tumour_lobe"]["value_counts"][0], {"value": "Frontal", "count": 2})
            self.assertFalse(variables["tumour_lobe"]["value_counts_truncated"])

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

        self.assertIn("lasso_logistic_regression", templates)
        self.assertEqual(templates["lasso_logistic_regression"]["category"], "Model Selection")
        self.assertEqual(templates["lasso_logistic_regression"]["cohort_display"], "shared_model_frame")
        self.assertIn("multivariable_logistic_regression", templates)
        self.assertEqual(templates["multivariable_logistic_regression"]["category"], "Regression Modeling")
        self.assertEqual(templates["multivariable_logistic_regression"]["cohort_display"], "shared_model_frame")
        self.assertIn("bootstrapped_multivariable_logistic_regression", templates)
        self.assertEqual(templates["bootstrapped_multivariable_logistic_regression"]["category"], "Model Validation")
        self.assertEqual(templates["bootstrapped_multivariable_logistic_regression"]["cohort_display"], "shared_model_frame")
        self.assertIn("hosmer_lemeshow_calibration", templates)
        self.assertEqual(templates["hosmer_lemeshow_calibration"]["category"], "Model Validation")
        self.assertEqual(templates["hosmer_lemeshow_calibration"]["cohort_display"], "shared_model_frame")
        self.assertEqual(templates["univariate_auc_screen"]["cohort_display"], "none")
        self.assertIn("cox_regression", templates)
        self.assertEqual(templates["cox_regression"]["category"], "Survival Modeling")
        self.assertEqual(templates["cox_regression"]["cohort_display"], "shared_model_frame")
        self.assertEqual(
            [parameter["name"] for parameter in templates["cox_regression"]["parameters"]],
            ["start_date", "event_date", "censor_date", "predictors"],
        )

    def test_multivariable_logistic_regression_builds_model_auc_and_terms(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42, "sex": "F"},
                {"recurrence": False, "nlr": 1.4, "age": 44, "sex": "M"},
                {"recurrence": False, "nlr": 1.6, "age": 47, "sex": "F"},
                {"recurrence": False, "nlr": 1.9, "age": 49, "sex": "M"},
                {"recurrence": False, "nlr": 2.1, "age": 52, "sex": "F"},
                {"recurrence": False, "nlr": 2.4, "age": 54, "sex": "M"},
                {"recurrence": True, "nlr": 5.2, "age": 60, "sex": "F"},
                {"recurrence": True, "nlr": 5.6, "age": 63, "sex": "M"},
                {"recurrence": True, "nlr": 6.0, "age": 65, "sex": "F"},
                {"recurrence": True, "nlr": 6.3, "age": 68, "sex": "M"},
                {"recurrence": True, "nlr": 6.8, "age": 70, "sex": "F"},
                {"recurrence": True, "nlr": 7.1, "age": 72, "sex": "M"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_multivariable_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age", "sex"]},
        )

        self.assertEqual(artifact["script_id"], "multivariable_logistic_regression")
        self.assertEqual(artifact["metadata"]["n"], 12)
        self.assertEqual(artifact["cohort_display"], "shared_model_frame")
        self.assertEqual(artifact["cohort"]["input_rows"], 12)
        self.assertEqual(artifact["cohort"]["included_rows"], 12)
        self.assertEqual(artifact["cohort"]["excluded_rows"], 0)
        self.assertEqual(artifact["cohort"]["required_fields"], ["recurrence", "nlr", "age", "sex"])
        self.assertEqual(artifact["metadata"]["predictor_count"], 3)
        self.assertGreaterEqual(artifact["metadata"]["term_count"], 3)
        self.assertGreaterEqual(artifact["metadata"]["auc"], 0.9)
        self.assertIsNotNone(artifact["metadata"]["cv_auc"])
        self.assertEqual(artifact["metadata"]["cv_folds"], 5)
        self.assertTrue(artifact["data"]["roc_curves"])
        self.assertTrue(all("odds_ratio" in row for row in artifact["data"]["rows"]))

    def test_multivariable_logistic_regression_reports_cv_fallback(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42},
                {"recurrence": False, "nlr": 1.4, "age": 44},
                {"recurrence": True, "nlr": 5.2, "age": 60},
                {"recurrence": True, "nlr": 5.6, "age": 63},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_multivariable_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age"]},
        )

        self.assertIsNone(artifact["metadata"]["cv_auc"])
        self.assertEqual(artifact["metadata"]["cv_folds"], 0)
        self.assertIn("Cross-validated AUC was not estimated", " ".join(artifact["data"]["warnings"]))

    def test_multivariable_logistic_regression_encodes_yes_no_variants_as_one_binary_term(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "residual_enhancement": "No"},
                {"recurrence": False, "residual_enhancement": "no"},
                {"recurrence": False, "residual_enhancement": "No - none seen"},
                {"recurrence": False, "residual_enhancement": "No"},
                {"recurrence": True, "residual_enhancement": "Yes"},
                {"recurrence": True, "residual_enhancement": "yes"},
                {"recurrence": True, "residual_enhancement": "Yes - inferolateral margin"},
                {"recurrence": True, "residual_enhancement": "Yes"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_multivariable_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["residual_enhancement"]},
        )

        self.assertEqual(artifact["metadata"]["term_count"], 1)
        self.assertEqual(artifact["data"]["rows"][0]["term"], "residual_enhancement: yes")

    def test_bootstrapped_multivariable_logistic_regression_uses_1000_resamples(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42, "sex": "F"},
                {"recurrence": False, "nlr": 1.4, "age": 44, "sex": "M"},
                {"recurrence": False, "nlr": 1.6, "age": 47, "sex": "F"},
                {"recurrence": False, "nlr": 1.9, "age": 49, "sex": "M"},
                {"recurrence": False, "nlr": 2.1, "age": 52, "sex": "F"},
                {"recurrence": False, "nlr": 2.4, "age": 54, "sex": "M"},
                {"recurrence": True, "nlr": 5.2, "age": 60, "sex": "F"},
                {"recurrence": True, "nlr": 5.6, "age": 63, "sex": "M"},
                {"recurrence": True, "nlr": 6.0, "age": 65, "sex": "F"},
                {"recurrence": True, "nlr": 6.3, "age": 68, "sex": "M"},
                {"recurrence": True, "nlr": 6.8, "age": 70, "sex": "F"},
                {"recurrence": True, "nlr": 7.1, "age": 72, "sex": "M"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_bootstrapped_multivariable_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age", "sex"]},
        )

        self.assertEqual(artifact["script_id"], "bootstrapped_multivariable_logistic_regression")
        self.assertEqual(artifact["metadata"]["bootstrap_resamples"], 1000)
        self.assertEqual(artifact["data"]["bootstrap_resamples"], 1000)
        self.assertEqual(artifact["metadata"]["validation_method"], "bootstrap_optimism")
        self.assertEqual(artifact["metadata"]["bootstrap_completed_resamples"], 1000)
        self.assertIsNotNone(artifact["metadata"]["optimism_corrected_auc"])
        self.assertTrue(all("bootstrap_ci_low" in row for row in artifact["data"]["rows"]))

    def test_hosmer_lemeshow_calibration_builds_grouped_test(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42, "sex": "F"},
                {"recurrence": False, "nlr": 1.4, "age": 44, "sex": "M"},
                {"recurrence": False, "nlr": 1.6, "age": 47, "sex": "F"},
                {"recurrence": True, "nlr": 1.9, "age": 49, "sex": "M"},
                {"recurrence": False, "nlr": 2.1, "age": 52, "sex": "F"},
                {"recurrence": False, "nlr": 2.4, "age": 54, "sex": "M"},
                {"recurrence": True, "nlr": 2.7, "age": 55, "sex": "F"},
                {"recurrence": False, "nlr": 3.0, "age": 56, "sex": "M"},
                {"recurrence": True, "nlr": 3.3, "age": 58, "sex": "F"},
                {"recurrence": False, "nlr": 3.7, "age": 59, "sex": "M"},
                {"recurrence": True, "nlr": 4.1, "age": 60, "sex": "F"},
                {"recurrence": True, "nlr": 4.4, "age": 61, "sex": "M"},
                {"recurrence": False, "nlr": 4.8, "age": 62, "sex": "F"},
                {"recurrence": True, "nlr": 5.2, "age": 63, "sex": "M"},
                {"recurrence": True, "nlr": 5.6, "age": 65, "sex": "F"},
                {"recurrence": False, "nlr": 5.9, "age": 66, "sex": "M"},
                {"recurrence": True, "nlr": 6.3, "age": 68, "sex": "F"},
                {"recurrence": True, "nlr": 6.8, "age": 70, "sex": "M"},
                {"recurrence": True, "nlr": 7.1, "age": 72, "sex": "F"},
                {"recurrence": True, "nlr": 7.5, "age": 74, "sex": "M"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_hosmer_lemeshow_calibration(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age", "sex"]},
        )

        self.assertEqual(artifact["script_id"], "hosmer_lemeshow_calibration")
        self.assertEqual(artifact["metadata"]["risk_groups"], 10)
        self.assertEqual(artifact["metadata"]["degrees_of_freedom"], 8)
        self.assertIsNotNone(artifact["metadata"]["p_value"])
        self.assertGreaterEqual(artifact["metadata"]["p_value"], 0)
        self.assertLessEqual(artifact["metadata"]["p_value"], 1)
        self.assertEqual(len(artifact["data"]["rows"]), 10)
        self.assertTrue(all("expected_events" in row for row in artifact["data"]["rows"]))

    def test_lasso_logistic_regression_selects_terms(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42, "sex": "F"},
                {"recurrence": False, "nlr": 1.4, "age": 44, "sex": "M"},
                {"recurrence": False, "nlr": 1.6, "age": 47, "sex": "F"},
                {"recurrence": False, "nlr": 1.9, "age": 49, "sex": "M"},
                {"recurrence": False, "nlr": 2.1, "age": 52, "sex": "F"},
                {"recurrence": False, "nlr": 2.4, "age": 54, "sex": "M"},
                {"recurrence": True, "nlr": 5.2, "age": 60, "sex": "F"},
                {"recurrence": True, "nlr": 5.6, "age": 63, "sex": "M"},
                {"recurrence": True, "nlr": 6.0, "age": 65, "sex": "F"},
                {"recurrence": True, "nlr": 6.3, "age": 68, "sex": "M"},
                {"recurrence": True, "nlr": 6.8, "age": 70, "sex": "F"},
                {"recurrence": True, "nlr": 7.1, "age": 72, "sex": "M"},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_lasso_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age", "sex"]},
        )

        self.assertEqual(artifact["script_id"], "lasso_logistic_regression")
        self.assertEqual(artifact["metadata"]["n"], 12)
        self.assertEqual(artifact["metadata"]["predictor_count"], 3)
        self.assertGreaterEqual(artifact["metadata"]["candidate_terms"], 3)
        self.assertEqual(artifact["metadata"]["selection_method"], "cross_validation")
        self.assertEqual(artifact["cohort_display"], "shared_model_frame")
        self.assertEqual(artifact["cohort"]["basis"], "complete_case")
        self.assertEqual(artifact["cohort"]["included_rows"], 12)
        self.assertEqual(artifact["metadata"]["selection_rule"], "lambda_1se")
        self.assertEqual(artifact["metadata"]["cv_folds"], 5)
        self.assertIsNotNone(artifact["metadata"]["lambda_min"])
        self.assertIsNotNone(artifact["metadata"]["lambda_1se"])
        self.assertGreaterEqual(artifact["metadata"]["selected_terms"], 1)
        self.assertGreaterEqual(artifact["metadata"]["auc"], 0.9)
        self.assertTrue(artifact["data"]["cv_path"])
        selected = [row for row in artifact["data"]["rows"] if row["selected"]]
        self.assertTrue(selected)
        self.assertTrue(all("odds_ratio" in row for row in artifact["data"]["rows"]))
        for row in artifact["data"]["rows"]:
            self.assertAlmostEqual(row["odds_ratio"], round(math.exp(row["coefficient"]), 3), places=3)
            self.assertEqual(row["abs_standardized_coefficient"], round(abs(row["standardized_coefficient"]), 4))

    def test_lasso_logistic_regression_uses_bic_fallback_when_cv_is_not_feasible(self) -> None:
        dataframe = pd.DataFrame(
            [
                {"recurrence": False, "nlr": 1.1, "age": 42},
                {"recurrence": False, "nlr": 1.4, "age": 44},
                {"recurrence": True, "nlr": 5.2, "age": 60},
                {"recurrence": True, "nlr": 5.6, "age": 63},
            ]
        )
        run_context = RunContext(run_id="20260510_120000", run_datetime="2026-05-10T12:00:00-04:00")

        artifact = build_lasso_logistic_regression(
            dataframe,
            run_context,
            "manifest_1",
            {"outcome": "recurrence", "predictors": ["nlr", "age"]},
        )

        self.assertEqual(artifact["metadata"]["selection_method"], "bic_fallback")
        self.assertEqual(artifact["metadata"]["selection_rule"], "bic")
        self.assertEqual(artifact["metadata"]["cv_folds"], 0)
        self.assertIsNone(artifact["metadata"]["lambda_min"])
        self.assertIn("Cross-validation was not feasible", artifact["data"]["warnings"][0])

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
        self.assertEqual(artifact["cohort_display"], "shared_model_frame")
        self.assertEqual(artifact["cohort"]["basis"], "valid_time_to_event_complete_case")
        self.assertEqual(artifact["cohort"]["included_rows"], 5)
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
            {
                "patient_id": "B",
                "recurrence": False,
                "age_at_presentation": 55,
                "tumour_lobe": "Temporal",
                "residual_enhancement": "Yes - inferolateral margin",
            },
            {"patient_id": "C", "recurrence": True, "age_at_presentation": 70, "tumour_lobe": "Frontal", "residual_enhancement": "no"},
            {"patient_id": "D", "recurrence": False, "age_at_presentation": None, "tumour_lobe": "Parietal", "residual_enhancement": "No"},
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

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.ingestion.adapters.gbm_registry import GBMRegistryAdapter


class RegistryIngestionManifestTests(unittest.TestCase):
    def test_registry_adapter_normalizes_tmz_as_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main_sheet_tmz.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,TMZ\n"
                "K0000001,01/01/1960,01/01/2020,60,Yes\n"
                "K0000002,01/01/1961,01/01/2020,59,yes\n"
                "K0000003,01/01/1962,01/01/2020,58,No\n",
                encoding="utf-8",
            )

            adapter = GBMRegistryAdapter()
            result = adapter.transform(adapter.load_raw(source_path), source_path)

            self.assertEqual(result.dataframe["tmz"].tolist(), [True, True, False])

    def test_registry_adapter_normalizes_residual_enhancement_yes_no_variants_as_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main_sheet_residual.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,Residual contrast enhancement\n"
                "K0000001,01/01/1960,01/01/2020,60,Yes\n"
                "K0000002,01/01/1961,01/01/2020,59,yes\n"
                "K0000003,01/01/1962,01/01/2020,58,Yes - inferolateral margin\n"
                "K0000004,01/01/1963,01/01/2020,57,No\n"
                "K0000005,01/01/1964,01/01/2020,56,no\n",
                encoding="utf-8",
            )

            adapter = GBMRegistryAdapter()
            result = adapter.transform(adapter.load_raw(source_path), source_path)

            self.assertEqual(result.dataframe["residual_enhancement"].tolist(), [True, True, True, False, False])

    def test_registry_adapter_reports_explicit_static_processing_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main_sheet_example.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,Neutrophils (presentation),"
                "Lymphocytes (presentation),Resection,First recurrence evidence,QMC Local\n"
                "K1234567,01/01/1960,01/01/2020,,4,2,02/01/2020,03/01/2021,QMC\n",
                encoding="utf-8",
            )

            adapter = GBMRegistryAdapter()
            result = adapter.transform(adapter.load_raw(source_path), source_path)
            step_ids = {step.step_id for step in result.steps}

            self.assertIn("main_sheet_example:derive_age", step_ids)
            self.assertIn("main_sheet_example:derive_resection_recurrence", step_ids)
            self.assertTrue(all(step.execution_mode == "static_code" for step in result.steps))
            self.assertTrue(all(step.source_file == "main_sheet_example.csv" for step in result.steps))

    def test_registry_adapter_handles_missing_age_inputs_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main_sheet_missing_age.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,Sex\n"
                "K0000001,,,,M\n",
                encoding="utf-8",
            )

            adapter = GBMRegistryAdapter()
            result = adapter.transform(adapter.load_raw(source_path), source_path)

            self.assertIsNone(result.dataframe["age_at_presentation"].iloc[0])
            self.assertEqual(result.dataframe["data_quality_flags"].iloc[0], ["missing_age_at_presentation"])

    def test_registry_adapter_handles_missing_recurrence_evidence_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main_sheet_missing_recurrence.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,First recurrence evidence,Sex\n"
                "K0000001,01/01/1960,01/01/2020,60,,M\n",
                encoding="utf-8",
            )

            adapter = GBMRegistryAdapter()
            result = adapter.transform(adapter.load_raw(source_path), source_path)

            self.assertIsNone(result.dataframe["recurrence_type"].iloc[0])
            self.assertIsNone(result.dataframe["recurrence_date"].iloc[0])


if __name__ == "__main__":
    unittest.main()

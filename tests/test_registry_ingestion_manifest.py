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


if __name__ == "__main__":
    unittest.main()

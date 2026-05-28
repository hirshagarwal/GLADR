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
from gladr.ingestion.workbench import (
    build_ingestion_workbench_payload,
    preview_ingestion_spec,
    run_ingestion_spec_from_ui,
)


class IngestionWorkbenchTests(unittest.TestCase):
    def test_workbench_exposes_default_spec_operations_and_static_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._make_project(Path(directory))

            payload = build_ingestion_workbench_payload(paths)
            adapter = payload["adapters"][0]
            operation_ids = {operation["operation"] for operation in adapter["operations"]}
            default_step_operations = {step["operation"] for step in adapter["default_spec"]["steps"]}
            static_code = next(operation for operation in adapter["operations"] if operation["operation"] == "static_code")

            self.assertEqual(adapter["adapter_id"], "gbm_registry")
            self.assertEqual(adapter["default_spec_source"], "packaged")
            self.assertIn("rename_columns", operation_ids)
            self.assertIn("filter_rows", operation_ids)
            self.assertIn("normalize_fields", operation_ids)
            self.assertIn("math", operation_ids)
            self.assertIn("derive_age", operation_ids)
            self.assertIn("join_data_file", operation_ids)
            self.assertIn("finalize_output", operation_ids)
            self.assertIn("filter_rows", default_step_operations)
            self.assertIn("normalize_fields", default_step_operations)
            self.assertIn("math", default_step_operations)
            self.assertIn("finalize_output", default_step_operations)
            self.assertEqual(adapter["default_spec"]["adapter_id"], "gbm_registry")
            self.assertIn("K-number", adapter["source_files"][0]["columns"])
            self.assertIn("patient_id", adapter["field_options"])
            self.assertTrue(any(file["kind"] == "histology_dataset" and file["is_latest"] for file in payload["data_files"]))
            self.assertTrue(any("marker" in file["columns"] for file in payload["data_files"] if file["kind"] == "histology_dataset"))
            histology_file = next(file for file in payload["data_files"] if file["kind"] == "histology_dataset")
            self.assertIn("IDH1 or IDH2 mutated", histology_file["column_values"]["marker"])
            functions = {function["function"] for function in static_code["functions"]}
            self.assertIn("gbm_registry.split_qmc_local", functions)
            self.assertIn("gbm_registry.derive_recurrence_type", functions)

    def test_preview_can_join_latest_histology_dataset_with_pivot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._make_project(Path(directory))
            payload = build_ingestion_workbench_payload(paths)
            adapter = payload["adapters"][0]
            histology_file = next(file for file in payload["data_files"] if file["kind"] == "histology_dataset")
            spec = json.loads(json.dumps(adapter["default_spec"]))
            finalize_index = next(index for index, step in enumerate(spec["steps"]) if step["operation"] == "finalize_output")
            spec["steps"].insert(
                finalize_index,
                {
                    "id": "join_histology",
                    "operation": "join_data_file",
                    "label": "Join histology markers",
                    "params": {
                        "file": histology_file["path"],
                        "left_key": "patient_id",
                        "right_key": "k_number",
                        "join_type": "left",
                        "columns": [],
                        "right_prefix": "",
                        "pivot": {
                            "index": "k_number",
                            "columns": "marker",
                            "values": "value",
                            "prefix": "histology__",
                        },
                    },
                }
            )

            preview = preview_ingestion_spec("gbm_registry", adapter["source_files"][0]["path"], spec, paths=paths)

            self.assertEqual(preview["rows"][0]["histology__IDH1 or IDH2 mutated"], "no")
            self.assertNotIn("qmc_local_raw", preview["rows"][0])

    def test_preview_applies_transient_spec_without_writing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._make_project(Path(directory))
            payload = build_ingestion_workbench_payload(paths)
            adapter = payload["adapters"][0]

            preview = preview_ingestion_spec(
                "gbm_registry",
                adapter["source_files"][0]["path"],
                adapter["default_spec"],
                paths=paths,
            )

            self.assertEqual(preview["summary"]["rows_ingested"], 1)
            patient_id_profile = next(variable for variable in preview["transformed_profile"]["variables"] if variable["name"] == "patient_id")
            self.assertEqual(patient_id_profile["value_counts"][0], {"value": "K0000001", "count": 1})
            self.assertEqual(preview["rows"][0]["patient_id"], "K0000001")
            self.assertEqual(preview["rows"][0]["nlr"], 2.0)
            self.assertEqual(preview["rows"][0]["qmc_local"], True)
            self.assertEqual(preview["rows"][0]["source"], "gbm_registry")
            self.assertEqual(preview["rows"][0]["data_quality_flags"], [])
            self.assertFalse(paths.registry_datasets_outputs_dir.exists())

    def test_preview_quality_report_includes_value_level_flag_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._make_project(Path(directory))
            source_path = paths.root / "data" / "raw" / "registry" / "main_sheet" / "main_sheet_example.csv"
            source_path.write_text(
                "K-number,DOB,Presentation Date,Age at presentation,Neutrophils (presentation),"
                "Lymphocytes (presentation),QMC Local\n"
                "K0000001,not-a-date,01/01/2020,60,4,2,QMC\n",
                encoding="utf-8",
            )
            payload = build_ingestion_workbench_payload(paths)
            adapter = payload["adapters"][0]

            preview = preview_ingestion_spec(
                "gbm_registry",
                adapter["source_files"][0]["path"],
                adapter["default_spec"],
                paths=paths,
            )

            report_row = preview["quality_report"][0]
            detail = next(item for item in report_row["flag_details"] if item["flag"] == "invalid_date_dob")
            self.assertIn("invalid_date_dob", report_row["flags"])
            self.assertEqual(detail["step_label"], "Normalize required dates")
            self.assertEqual(detail["step_position"], 4)
            self.assertEqual(detail["operation"], "normalize_fields")
            self.assertEqual(detail["field"], "dob")
            self.assertEqual(detail["raw_value"], "not-a-date")
            self.assertIn("date", detail["hint"])

    def test_ui_run_writes_registry_artifacts_under_supplied_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self._make_project(Path(directory))
            payload = build_ingestion_workbench_payload(paths)
            adapter = payload["adapters"][0]
            spec = json.loads(json.dumps(adapter["default_spec"]))
            spec["steps"][0]["label"] = "Saved map source columns"

            written = run_ingestion_spec_from_ui(
                "gbm_registry",
                adapter["source_files"][0]["path"],
                spec,
                paths=paths,
            )

            self.assertTrue(written["clean_dataset"].exists())
            self.assertTrue(written["manifest"].exists())
            self.assertTrue((paths.canonical_ingestion_outputs_dir / "latest.json").exists())
            manifest = json.loads(written["manifest"].read_text(encoding="utf-8"))
            self.assertTrue(manifest["specs"][0]["transient"])
            self.assertEqual(manifest["specs"][0]["adapter_id"], "gbm_registry")
            saved_spec_path = paths.ingestion_specs_dir / "gbm_registry.json"
            saved_spec = json.loads(saved_spec_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_spec["steps"][0]["label"], "Saved map source columns")
            self.assertNotIn("transient", saved_spec)
            updated_payload = build_ingestion_workbench_payload(paths)
            updated_adapter = updated_payload["adapters"][0]
            self.assertEqual(updated_adapter["default_spec_source"], "saved")
            self.assertEqual(updated_adapter["default_spec"]["steps"][0]["label"], "Saved map source columns")

    def _make_project(self, root: Path) -> ProjectPaths:
        source_dir = root / "data" / "raw" / "registry" / "main_sheet"
        reference_dir = root / "data" / "reference"
        histology_dir = root / "outputs" / "ingestion" / "histology"
        histology_dataset_dir = histology_dir / "datasets"
        source_dir.mkdir(parents=True)
        reference_dir.mkdir(parents=True)
        histology_dataset_dir.mkdir(parents=True)
        (reference_dir / "lobe_mapping.json").write_text("{}", encoding="utf-8")
        (source_dir / "main_sheet_example.csv").write_text(
            "K-number,DOB,Presentation Date,Age at presentation,Neutrophils (presentation),"
            "Lymphocytes (presentation),QMC Local\n"
            "K0000001,01/01/1960,01/01/2020,,4,2,QMC\n",
            encoding="utf-8",
        )
        (histology_dataset_dir / "histology_dataset_test.json").write_text(
            json.dumps(
                {
                    "run_id": "test",
                    "records": [
                        {
                            "k_number": "K0000001",
                            "marker": "IDH1 or IDH2 mutated",
                            "value": "no",
                            "notes": "",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (histology_dir / "latest.json").write_text(
            json.dumps({"histology_dataset": "datasets/histology_dataset_test.json"}),
            encoding="utf-8",
        )
        return ProjectPaths.from_root(root)


if __name__ == "__main__":
    unittest.main()

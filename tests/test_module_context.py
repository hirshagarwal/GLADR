from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src" / "gladr"


class ModuleContextTests(unittest.TestCase):
    def test_stage_modules_have_llm_context_packets(self) -> None:
        expected_files = {
            "ingestion": [
                "README.md",
                "module.yaml",
                "contracts/canonical_schema.json",
                "contracts/ingestion_artifact_schema.json",
                "examples/gbm_registry_raw_sample.csv",
                "examples/clean_dataset_sample.json",
                "examples/ingestion_report_sample.json",
            ],
            "analysis": [
                "README.md",
                "module.yaml",
                "contracts/clean_dataset_schema.json",
                "contracts/analysis_artifact_schema.json",
                "contracts/visualization_schema.json",
                "examples/clean_dataset_sample.json",
                "examples/cohort_summary_artifact.json",
                "examples/age_distribution_artifact.json",
            ],
            "dashboard": [
                "README.md",
                "module.yaml",
                "contracts/dashboard_payload_schema.json",
                "contracts/visualization_schema.json",
                "examples/dashboard_payload_sample.json",
            ],
        }

        for module_name, paths in expected_files.items():
            with self.subTest(module=module_name):
                module_root = SRC_DIR / module_name
                for path in paths:
                    self.assertTrue((module_root / path).exists(), f"Missing {module_name}/{path}")

                readme = (module_root / "README.md").read_text(encoding="utf-8")
                module_yaml = (module_root / "module.yaml").read_text(encoding="utf-8")
                self.assertIn("LLM edit scope", readme)
                self.assertIn("module_id:", module_yaml)
                self.assertIn("llm_rules:", module_yaml)

    def test_module_json_context_files_are_valid(self) -> None:
        for module_root in (SRC_DIR / "ingestion", SRC_DIR / "analysis", SRC_DIR / "dashboard"):
            for json_path in [*module_root.glob("contracts/*.json"), *module_root.glob("examples/*.json")]:
                with self.subTest(path=json_path):
                    with json_path.open("r", encoding="utf-8") as handle:
                        json.load(handle)

    def test_mirrored_contracts_match_runtime_contracts(self) -> None:
        runtime_contracts = SRC_DIR / "contracts"

        mirrored_pairs = [
            (runtime_contracts / "canonical_schema.json", SRC_DIR / "ingestion" / "contracts" / "canonical_schema.json"),
            (runtime_contracts / "canonical_schema.json", SRC_DIR / "analysis" / "contracts" / "clean_dataset_schema.json"),
            (runtime_contracts / "visualization_schema.json", SRC_DIR / "analysis" / "contracts" / "visualization_schema.json"),
            (runtime_contracts / "visualization_schema.json", SRC_DIR / "dashboard" / "contracts" / "visualization_schema.json"),
        ]

        for runtime_path, mirrored_path in mirrored_pairs:
            with self.subTest(path=mirrored_path):
                self.assertEqual(
                    json.loads(runtime_path.read_text(encoding="utf-8")),
                    json.loads(mirrored_path.read_text(encoding="utf-8")),
                )


if __name__ == "__main__":
    unittest.main()

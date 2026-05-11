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
from gladr.ingestion.histology import compile_histology_csvs, extract_k_number, run_histology_ingestion


class HistologyIngestionTests(unittest.TestCase):
    def test_extracts_k_number_from_filename_with_suffix(self) -> None:
        self.assertEqual(extract_k_number("K1463292 (2 years later).txt"), "K1463292")

    def test_compile_histology_csvs_adds_k_number_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "K1234567.csv"
            csv_path.write_text(
                "marker,value,notes\n"
                "IDH1 or IDH2 mutated,no,\n"
                "MGMT promoter methylation status,methylated,\n",
                encoding="utf-8",
            )

            combined = compile_histology_csvs([csv_path])

            self.assertEqual(list(combined.columns), ["k_number", "marker", "value", "notes"])
            self.assertEqual(combined["k_number"].tolist(), ["K1234567", "K1234567"])

    def test_run_histology_ingestion_compile_only_writes_combined_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = _project_paths(root)
            txt_dir = paths.histology_text_reports_dir
            csv_dir = paths.histology_marker_csv_dir
            txt_dir.mkdir(parents=True)
            csv_dir.mkdir(parents=True)

            (txt_dir / "K1234567.txt").write_text("Histology report text", encoding="utf-8")
            (csv_dir / "K1234567.csv").write_text(
                "marker,value,notes\nIDH1 or IDH2 mutated,no,\n",
                encoding="utf-8",
            )

            result = run_histology_ingestion(generate_reports=False, paths=paths)

            dataset_path = result["histology_dataset"]
            self.assertTrue(dataset_path.exists())
            payload = json.loads(dataset_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["records"][0]["k_number"], "K1234567")
            self.assertEqual(payload["total_rows"], 1)
            self.assertTrue((paths.histology_ingestion_outputs_dir / "latest.json").exists())
            self.assertTrue(result["manifest"].exists())
            self.assertTrue(result["extraction_report"].exists())
            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["summary"]["total_rows"], 1)
            self.assertEqual(manifest["steps"][0]["step_id"], "read_text_reports")
            self.assertEqual(manifest["steps"][1]["execution_mode"], "static_code")


def _project_paths(root: Path) -> ProjectPaths:
    return ProjectPaths.from_root(root)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.analysis.base_script import BaseAnalysisScript
from gladr.core.discovery import discover_subclasses
from gladr.ingestion.adapters.base_adapter import BaseAdapter


class DiscoveryTests(unittest.TestCase):
    def test_discovers_ingestion_adapters(self) -> None:
        adapters = discover_subclasses("gladr.ingestion.adapters", BaseAdapter)
        adapter_ids = {adapter.adapter_id for adapter in adapters}
        self.assertIn("gbm_registry", adapter_ids)
        self.assertIn("generic_csv", adapter_ids)

    def test_discovers_analysis_scripts(self) -> None:
        scripts = discover_subclasses("gladr.analysis.scripts", BaseAnalysisScript)
        script_ids = {script.script_id for script in scripts}
        self.assertTrue({"cohort_summary", "age_distribution", "sex_breakdown"}.issubset(script_ids))


if __name__ == "__main__":
    unittest.main()

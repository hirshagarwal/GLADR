from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.dashboard.server import _dashboard_payload


class DashboardServerTests(unittest.TestCase):
    def test_empty_dashboard_payload_supports_first_run_ui(self) -> None:
        with patch("gladr.dashboard.server.list_registered_projects", return_value={"active_project": None, "projects": []}):
            payload = _dashboard_payload(None)

        self.assertIsNone(payload["project"])
        self.assertEqual(payload["summary"]["ingestion_runs"], 0)
        self.assertEqual(payload["ingestion_runs"], [])
        self.assertEqual(payload["analyses"], [])
        self.assertIn("analysis_templates", payload)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.core.latest_pointer import read_latest_pointer, write_latest_pointer


class LatestPointerTests(unittest.TestCase):
    def test_write_and_read_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            payload = {"demo": "artifact.json"}

            write_latest_pointer(path, payload)

            self.assertEqual(read_latest_pointer(path), payload)


if __name__ == "__main__":
    unittest.main()

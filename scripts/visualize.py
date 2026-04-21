"""Compatibility wrapper for the dashboard builder."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.dashboard.build import build_dashboard


if __name__ == "__main__":
    build_dashboard()

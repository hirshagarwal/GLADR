"""Helpers for loading dashboard manifest inputs."""

from __future__ import annotations

import json
from pathlib import Path


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

"""Helpers for loading packaged contract files."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_contract(name: str) -> dict[str, Any]:
    with resources.files("gladr.contracts").joinpath(name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_field_names() -> list[str]:
    schema = load_contract("canonical_schema.json")
    return [field["name"] for field in schema["fields"]]

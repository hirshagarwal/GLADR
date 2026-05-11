"""Row-level quality flag helpers."""

from __future__ import annotations

from collections.abc import Iterable


def unique_flags(flags: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for flag in flags:
        if not flag or flag in seen:
            continue
        ordered.append(flag)
        seen.add(flag)

    return ordered

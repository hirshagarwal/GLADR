"""Dynamic module discovery for adapters and analysis scripts."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterable
from typing import TypeVar


T = TypeVar("T")


def discover_subclasses(package_name: str, base_class: type[T]) -> list[type[T]]:
    package = importlib.import_module(package_name)
    discovered: list[type[T]] = []

    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        module = importlib.import_module(module_info.name)
        for _, member in inspect.getmembers(module, inspect.isclass):
            if member is base_class:
                continue
            if not issubclass(member, base_class):
                continue
            if inspect.isabstract(member):
                continue
            discovered.append(member)

    return sorted(discovered, key=lambda item: item.__name__)


def instantiate_discovered(package_name: str, base_class: type[T]) -> list[T]:
    return [member() for member in discover_subclasses(package_name, base_class)]


def filter_by_ids(items: Iterable[T], ids: set[str], attribute: str) -> list[T]:
    return [item for item in items if getattr(item, attribute) in ids]

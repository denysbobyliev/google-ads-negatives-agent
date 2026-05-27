from __future__ import annotations

"""Helpers for loading the active vertical's implementation modules.

Root pipeline stages should depend on this adapter, not on a concrete
``verticals.<name>`` package. That keeps account/vertical doctrine swappable
without scattering vertical-specific imports through the orchestration code.
"""

import importlib
import os
from types import ModuleType

import config


def load_module(module_name: str) -> ModuleType:
    module_path = f"verticals.{config.VERTICAL_KEY}.{module_name}"
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        vertical_dir = os.path.join(config.VERTICALS_DIR, config.VERTICAL_KEY)
        raise ModuleNotFoundError(
            f"Active vertical '{config.VERTICAL_KEY}' is missing module '{module_name}'. "
            f"Expected it under {vertical_dir}."
        ) from exc


def build_anchor_index(inventory: dict[str, str]):
    return load_module("geo_anchor_map").build_anchor_index(inventory)


def detect_geo(term: str, idx):
    return load_module("geo_gate").detect_geo(term, idx)


def route_decision(*args, **kwargs):
    return load_module("geo_gate").route_decision(*args, **kwargs)


def served_anchor_in_term(*args, **kwargs) -> bool:
    return bool(load_module("geo_gate").served_anchor_in_term(*args, **kwargs))

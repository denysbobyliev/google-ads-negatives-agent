from __future__ import annotations
"""Load vertical target/ad-group anchor definitions."""

import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import config


def load_targets() -> dict[str, dict]:
    path = config.TARGETS_YAML
    if not os.path.exists(path):
        path = config.REGIONS_YAML
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("regions", {})


def get_target_keys() -> set[str]:
    return set(load_targets().keys())


def get_all_own_anchors() -> set[str]:
    anchors = set()
    for target in load_targets().values():
        for anchor in target.get("own_anchors", []):
            anchors.add(anchor.lower().strip())
    return anchors

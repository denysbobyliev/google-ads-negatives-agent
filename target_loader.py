from __future__ import annotations
"""Load vertical target/ad-group anchor definitions."""

import os
import re
import sys
import unicodedata

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import config


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower().strip()).encode(
        "ascii", "ignore"
    ).decode("ascii")


def load_targets() -> dict[str, dict]:
    path = config.TARGETS_YAML
    if not os.path.exists(path):
        path = config.REGIONS_YAML
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("regions", {})


def compile_anchor_patterns(
    anchors: list[str],
    policy: dict,
) -> tuple[list[tuple[str, re.Pattern]], list[dict]]:
    concatenation = policy.get("concatenation", {})
    enabled = concatenation.get("enabled", True)
    min_anchor_length = int(concatenation.get("min_anchor_length", 4))
    exclude_within = {
        _normalize(anchor): tokens
        for anchor, tokens in (concatenation.get("exclude_within", {}) or {}).items()
    }

    standalone_patterns = []
    substring_anchors = []
    for anchor in anchors:
        normalized = _normalize(anchor)
        standalone_patterns.append(
            (anchor, re.compile(r"\b" + re.escape(normalized) + r"\b"))
        )
        if not enabled or len(normalized) < min_anchor_length:
            continue
        excluded = exclude_within.get(normalized, [])
        substring_anchors.append(
            {
                "anchor": normalized,
                "length": len(normalized),
                "excluded_tokens": {_normalize(token) for token in excluded},
            }
        )
    return standalone_patterns, substring_anchors


def load_anchor_patterns(policy: dict | None = None) -> dict[str, dict]:
    if policy is None:
        policy = config.load_policy(config.POLICY_YAML)

    universe = {}
    for region_key, region in load_targets().items():
        own_standalone, own_substring = compile_anchor_patterns(
            region.get("own_anchors", []),
            policy,
        )
        sibling_standalone, sibling_substring = compile_anchor_patterns(
            region.get("sibling_anchors", []),
            policy,
        )
        universe[region_key] = {
            "own": own_standalone,
            "own_substring": own_substring,
            "own_raw": {a.lower() for a in region.get("own_anchors", [])},
            "sibling": sibling_standalone,
            "sibling_substring": sibling_substring,
            "concatenation_enabled": policy.get("concatenation", {}).get("enabled", True),
        }
    return universe


def get_target_keys() -> set[str]:
    return set(load_targets().keys())


def get_all_own_anchors() -> set[str]:
    anchors = set()
    for target in load_targets().values():
        for anchor in target.get("own_anchors", []):
            anchors.add(anchor.lower().strip())
    return anchors

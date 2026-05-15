from __future__ import annotations
"""Validate vertical target definitions before running the pipeline."""

import argparse
from collections import defaultdict
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import target_loader


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower().strip()).encode(
        "ascii", "ignore"
    ).decode("ascii")


def _find_own_anchor_collisions(targets: dict[str, dict]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = defaultdict(list)
    for key, target in targets.items():
        for anchor in target.get("own_anchors", []):
            seen[_normalize(anchor)].append(key)
    return {anchor: keys for anchor, keys in seen.items() if len(set(keys)) > 1}


def _find_missing_required_fields(targets: dict[str, dict]) -> list[str]:
    missing = []
    for key, target in targets.items():
        for field in ("target_region_label", "own_anchors"):
            if not target.get(field):
                missing.append(f"{key}: missing {field}")
    return missing


def _find_duplicate_own_anchors(targets: dict[str, dict]) -> list[str]:
    duplicates = []
    for key, target in targets.items():
        anchors = [_normalize(anchor) for anchor in target.get("own_anchors", [])]
        repeated = sorted({anchor for anchor in anchors if anchors.count(anchor) > 1})
        for anchor in repeated:
            duplicates.append(f"{key}: duplicate own_anchor '{anchor}'")
    return duplicates


def _find_sibling_drift(targets: dict[str, dict]) -> tuple[list[str], list[str]]:
    all_own_by_target = {
        key: {_normalize(anchor) for anchor in target.get("own_anchors", [])}
        for key, target in targets.items()
    }
    all_own = set().union(*all_own_by_target.values()) if all_own_by_target else set()

    missing = []
    extra = []
    for key, target in targets.items():
        expected = all_own - all_own_by_target[key]
        actual = {_normalize(anchor) for anchor in target.get("sibling_anchors", [])}
        missing_count = len(expected - actual)
        extra_count = len(actual - expected)
        if missing_count:
            missing.append(f"{key}: missing {missing_count} derived sibling anchor(s)")
        if extra_count:
            extra.append(f"{key}: has {extra_count} sibling anchor(s) not owned by another target")
    return missing, extra


def _find_stale_concatenation_excludes(targets: dict[str, dict], policy: dict) -> list[str]:
    active_anchors = set()
    for target in targets.values():
        for anchor in target.get("own_anchors", []):
            active_anchors.add(_normalize(anchor))
        for anchor in target.get("sibling_anchors", []):
            active_anchors.add(_normalize(anchor))

    exclude_within = policy.get("concatenation", {}).get("exclude_within", {}) or {}
    warnings = []
    for anchor in sorted(exclude_within):
        normalized = _normalize(anchor)
        if normalized not in active_anchors:
            warnings.append(
                f"concatenation.exclude_within key '{anchor}' is not an active anchor"
            )
    return warnings


def validate(strict_siblings: bool = False) -> int:
    targets = target_loader.load_targets()
    policy = config.load_policy(config.POLICY_YAML)
    errors = []
    warnings = []

    if not targets:
        errors.append(f"No targets found in {config.TARGETS_YAML}")

    errors.extend(_find_missing_required_fields(targets))
    errors.extend(_find_duplicate_own_anchors(targets))

    collisions = _find_own_anchor_collisions(targets)
    for anchor, keys in sorted(collisions.items()):
        errors.append(f"own_anchor collision '{anchor}' used by {', '.join(sorted(set(keys)))}")

    if strict_siblings:
        sibling_missing, sibling_extra = _find_sibling_drift(targets)
        errors.extend(sibling_missing)
        errors.extend(sibling_extra)

    warnings.extend(_find_stale_concatenation_excludes(targets, policy))

    print(f"Validated {len(targets)} targets from {config.TARGETS_YAML}")
    for warning in warnings[:20]:
        print(f"WARNING: {warning}")
    if len(warnings) > 20:
        print(f"WARNING: ... {len(warnings) - 20} more warning(s)")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"Target validation failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"Target validation passed: 0 error(s), {len(warnings)} warning(s)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate target/anchor definitions")
    parser.add_argument(
        "--strict-siblings",
        action="store_true",
        help="Fail when sibling_anchors drift from the derived cross-target anchor set",
    )
    args = parser.parse_args()
    raise SystemExit(validate(strict_siblings=args.strict_siblings))


if __name__ == "__main__":
    main()

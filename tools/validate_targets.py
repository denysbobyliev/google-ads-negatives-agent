from __future__ import annotations
"""Validate the classifier ACCOUNT BLOCK before running the pipeline."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def validate() -> int:
    errors = []
    cfg = config.load_account_config()

    for key in ("generals", "sub_regions", "language_map", "tiebreakers", "special_cases"):
        if key not in cfg:
            errors.append(f"ACCOUNT BLOCK missing '{key}'")

    generals = cfg.get("generals", {})
    if not isinstance(generals, dict) or not generals:
        errors.append("ACCOUNT BLOCK generals must be a non-empty mapping")

    language_map = cfg.get("language_map", {})
    if not isinstance(language_map, dict):
        errors.append("ACCOUNT BLOCK language_map must be a mapping")
    else:
        for lang, countries in language_map.items():
            if not isinstance(countries, list):
                errors.append(f"language_map.{lang} must be a list")

    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"Classifier ACCOUNT BLOCK validation failed: {len(errors)} error(s)")
        return 1

    print(
        "Classifier ACCOUNT BLOCK validation passed: "
        f"{len(generals)} campaign generals, {len(language_map)} language maps"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate classifier ACCOUNT BLOCK")
    parser.parse_args()
    raise SystemExit(validate())


if __name__ == "__main__":
    main()

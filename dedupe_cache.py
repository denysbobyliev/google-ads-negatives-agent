from __future__ import annotations
"""
Stage 4: Deduplicate Against Cache
Skip any served ad-group/term pair already in data/classified_terms.json.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config


def _legacy_key(entry: dict) -> tuple[str, str]:
    return (entry.get("region_key") or entry.get("ad_group_name", ""), entry["term"])


def _scoped_key(entry: dict) -> tuple[str, str, str, str]:
    return (
        entry.get("account_key", config.ACCOUNT_KEY),
        entry.get("vertical_key", config.VERTICAL_KEY),
        entry.get("ad_group_name") or entry.get("region_key", ""),
        entry["term"],
    )


def load_cache() -> tuple[set[tuple[str, str]], set[tuple[str, str, str, str]]]:
    if not os.path.exists(config.CLASSIFIED_TERMS_PATH):
        return set(), set()
    with open(config.CLASSIFIED_TERMS_PATH) as f:
        cache = json.load(f)
    legacy = set()
    scoped = set()
    for entry in cache:
        if "term" not in entry:
            continue
        if "region_key" not in entry and "ad_group_name" not in entry:
            continue
        if "account_key" in entry or "vertical_key" in entry:
            scoped.add(_scoped_key(entry))
        else:
            # Backward compatibility for the original single-account cache.
            legacy.add(_legacy_key(entry))
    return legacy, scoped


def run(terms: list[dict], ignore_cache: bool = False) -> list[dict]:
    t0 = time.time()

    if ignore_cache:
        elapsed = time.time() - t0
        print(
            f"Stage 4 — dedupe_cache: SKIPPED (--ignore-cache), "
            f"passing all {len(terms)} terms through (in {elapsed:.1f}s)"
        )
        return terms

    legacy_seen, scoped_seen = load_cache()

    fresh = []
    skipped = 0
    for t in terms:
        served_key = t.get("ad_group_name", "")
        legacy_key = (served_key, t["term"])
        scoped_key = (config.ACCOUNT_KEY, config.VERTICAL_KEY, served_key, t["term"])
        if legacy_key in legacy_seen or scoped_key in scoped_seen:
            skipped += 1
        else:
            fresh.append(t)

    elapsed = time.time() - t0
    print(
        f"Stage 4 — dedupe_cache: {len(fresh)} new, {skipped} already cached "
        f"(in {elapsed:.1f}s)"
    )
    return fresh

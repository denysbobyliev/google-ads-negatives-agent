from __future__ import annotations
"""
Stage 4: Deduplicate Against Cache
Skip any (region_key, term) already in data/classified_terms.json.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config


def load_cache() -> set[tuple[str, str]]:
    if not os.path.exists(config.CLASSIFIED_TERMS_PATH):
        return set()
    with open(config.CLASSIFIED_TERMS_PATH) as f:
        cache = json.load(f)
    return {(entry["region_key"], entry["term"]) for entry in cache}


def run(terms: list[dict], ignore_cache: bool = False) -> list[dict]:
    t0 = time.time()

    if ignore_cache:
        elapsed = time.time() - t0
        print(
            f"Stage 4 — dedupe_cache: SKIPPED (--ignore-cache), "
            f"passing all {len(terms)} terms through (in {elapsed:.1f}s)"
        )
        return terms

    seen = load_cache()

    fresh = []
    skipped = 0
    for t in terms:
        key = (t["region_key"], t["term"])
        if key in seen:
            skipped += 1
        else:
            fresh.append(t)

    elapsed = time.time() - t0
    print(
        f"Stage 4 — dedupe_cache: {len(fresh)} new, {skipped} already cached "
        f"(in {elapsed:.1f}s)"
    )
    return fresh

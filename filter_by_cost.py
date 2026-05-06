from __future__ import annotations
"""
Stage 3: Filter by Cost
- Mark terms with conversions_value >= CV_PROTECTION_THRESHOLD as PROTECTED (never negate).
- Drop terms with cost < COST_THRESHOLD (not enough spend to bother classifying).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config


def run(terms: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (active_terms, protected_terms, below_threshold_terms).
    active_terms         : cost >= threshold, not protected — main pipeline.
    protected_terms      : CV >= threshold — never negate, cached as PROTECTED.
    below_threshold_terms: cost < threshold — passed to banned-words check only,
                           skipped by regex/LLM/upload.
    """
    t0 = time.time()

    active = []
    protected = []
    below_threshold = []

    for t in terms:
        if t["conversions_value"] >= config.CV_PROTECTION_THRESHOLD:
            t["decision"] = "PROTECTED"
            t["confidence"] = None
            t["source"] = None
            t["target_scope"] = "none"
            t["anchor_found"] = None
            t["reason"] = f"conversions_value={t['conversions_value']:.2f} >= {config.CV_PROTECTION_THRESHOLD}"
            protected.append(t)
        elif t["cost"] < config.COST_THRESHOLD:
            below_threshold.append(t)
        else:
            active.append(t)

    elapsed = time.time() - t0
    print(
        f"Stage 3 — filter_by_cost: {len(active)} active, "
        f"{len(protected)} protected, {len(below_threshold)} below cost threshold "
        f"(in {elapsed:.1f}s)"
    )
    return active, protected, below_threshold

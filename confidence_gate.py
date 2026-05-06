from __future__ import annotations
"""
Stage 7: Confidence Gate
Applies score threshold to LLM-classified terms.
  score >= 5 → KEEP (term is relevant enough to this ad group's audience)
  score <  5 → NEGATE at ad group level
Regex-decided terms pass through unchanged (regex decisions are deterministic).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config

SCORE_THRESHOLD = 6


def run(
    regex_decided: list[dict],
    llm_classified: list[dict],
) -> list[dict]:
    """
    Returns a flat list of all terms with decision/confidence fields set,
    ready for scope_router.
    """
    t0 = time.time()

    result = list(regex_decided)
    negate_count = 0
    keep_count = 0

    for t in llm_classified:
        score = t.get("llm_score", SCORE_THRESHOLD)
        t["score"] = score
        t["confidence"] = str(score)
        t["anchor_found"] = t.get("llm_anchor")
        t["reason"] = t.get("llm_reason", "")
        t["source"] = "llm"
        if score < SCORE_THRESHOLD:
            if config.DEFER_NEGATE_SCORE is not None and score == config.DEFER_NEGATE_SCORE:
                t["decision"] = "DEFER"
            else:
                t["decision"] = "NEGATE"
            negate_count += 1
        else:
            t["decision"] = "KEEP"
            keep_count += 1
        result.append(t)

    elapsed = time.time() - t0
    print(
        f"Stage 7 — confidence_gate: {len(regex_decided)} regex + "
        f"{negate_count} LLM-negate + {keep_count} LLM-keep "
        f"(in {elapsed:.3f}s)"
    )
    return result

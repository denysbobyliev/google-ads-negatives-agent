from __future__ import annotations
"""
Stage 8: Scope Router
Routes every NEGATE decision to exactly one scope:

  AD GROUP LEVEL — all negations land here
    - regex source (sibling match from Stage 5): term explicitly belongs to a
      different regional ad group → negate at the landing ad group only
    - LLM NEGATE (any reason): negate at the landing ad group only

  KEEP → target_scope="none", no action

  campaign_level is always empty — campaign-level negation is not done
  automatically. The caller still receives the list for future use.

Rationale: negate conservatively. A term that misbehaved in one ad group
should be excluded there. Other ad groups in the same campaign are unaffected
until evidence accumulates. LLM terms that happen to share an anchor with a
known region route to AG-level just like everything else.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config


def run(terms: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (ag_level, campaign_level, keep_terms).
    campaign_level is always empty — all negations are AG-level.
    """
    t0 = time.time()

    ag_level = []
    campaign_level: list[dict] = []
    keep_terms = []

    for t in terms:
        decision = t.get("decision", "KEEP")

        if decision not in ("NEGATE", "DEFER"):
            t["target_scope"] = "none"
            keep_terms.append(t)
            continue

        anchor = t.get("anchor_found") or t.get("llm_anchor") or t.get("regex_anchor")
        t["anchor_found"] = anchor
        t["target_scope"] = "ad_group"
        ag_level.append(t)

    elapsed = time.time() - t0
    print(
        f"Stage 8 — scope_router: {len(ag_level)} AG-level, "
        f"{len(keep_terms)} KEEP (in {elapsed:.1f}s)"
    )
    return ag_level, campaign_level, keep_terms

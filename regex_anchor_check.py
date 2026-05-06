from __future__ import annotations
"""
Stage 5: Regex Anchor Check
Fast first pass before touching the LLM.

For each term in ad group of region R:
  - Own anchors  (R.own_anchors)     → whole-word match → KEEP  (correctly targeted)
  - Sibling anchors (R.sibling_anchors) → whole-word match → NEGATE_AG (wrong ad group)
  - No match                          → PASS (send to LLM)

sibling_anchors are pre-computed in regions.yaml — no runtime cross-region join needed.

"Whole-word" = anchor surrounded by \b after lowercasing.
Multi-word anchors (e.g. "chiang mai") are matched with \b on the outer edges only.
"""

import os
import re
import sys
import time
import unicodedata
import yaml

sys.path.insert(0, os.path.dirname(__file__))
import config


def _normalize(text: str) -> str:
    """Lowercase + strip accents so 'español' matches 'espanol'."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")


def _compile_anchors(anchors: list[str]) -> list[tuple[str, re.Pattern]]:
    patterns = []
    for anchor in anchors:
        pattern = re.compile(r"\b" + re.escape(_normalize(anchor)) + r"\b")
        patterns.append((anchor, pattern))
    return patterns


def load_anchor_universe() -> dict:
    """
    Returns {region_key: {"own": compiled_patterns, "own_raw": set,
                          "sibling": compiled_patterns}}
    """
    with open(config.REGIONS_YAML) as f:
        regions = yaml.safe_load(f)["regions"]

    universe = {}
    for rk, region in regions.items():
        universe[rk] = {
            "own": _compile_anchors(region["own_anchors"]),
            "own_raw": {a.lower() for a in region["own_anchors"]},
            "sibling": _compile_anchors(region.get("sibling_anchors", [])),
        }
    return universe


def _find_match(term: str, compiled: list[tuple[str, re.Pattern]]) -> str | None:
    term_norm = _normalize(term)
    for anchor, pattern in compiled:
        if pattern.search(term_norm):
            return anchor
    return None


def run(terms: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Returns (llm_candidates, regex_decided).
    llm_candidates : no regex match found → needs LLM classification
    regex_decided  : KEEP or NEGATE_AG decided by regex — skip LLM
    """
    t0 = time.time()
    universe = load_anchor_universe()

    llm_candidates = []
    regex_decided = []
    keep_count = 0
    negate_ag_count = 0
    pass_count = 0

    for t in terms:
        rk = t["region_key"]
        term = t["term"]
        region_data = universe[rk]

        # Sibling checked before own: a term that explicitly references another
        # region (e.g. "tobago") should be negated even if it also contains an
        # own anchor (e.g. "trinidad" for Cuba, which is both a Cuban city and
        # part of "Trinidad and Tobago").
        sibling_match = _find_match(term, region_data["sibling"])
        if sibling_match:
            t["regex_result"] = "NEGATE_AG"
            t["regex_anchor"] = sibling_match
            t["decision"] = "NEGATE"
            t["confidence"] = "high"
            t["source"] = "regex"
            t["target_scope"] = "ad_group"
            t["anchor_found"] = sibling_match
            t["reason"] = f"sibling anchor '{sibling_match}' found — wrong ad group"
            regex_decided.append(t)
            negate_ag_count += 1
            continue

        own_match = _find_match(term, region_data["own"])
        if own_match:
            t["regex_result"] = "KEEP"
            t["regex_anchor"] = own_match
            t["decision"] = "KEEP"
            t["confidence"] = "high"
            t["source"] = "regex"
            t["target_scope"] = "none"
            t["anchor_found"] = own_match
            t["reason"] = f"own anchor '{own_match}' found — correctly targeted"
            regex_decided.append(t)
            keep_count += 1
            continue

        t["regex_result"] = "PASS"
        t["regex_anchor"] = None
        llm_candidates.append(t)
        pass_count += 1

    elapsed = time.time() - t0
    print(
        f"Stage 5 — regex_anchor_check: "
        f"{keep_count} KEEP, {negate_ag_count} NEGATE_AG, {pass_count} → LLM "
        f"(in {elapsed:.1f}s)"
    )
    return llm_candidates, regex_decided


def get_all_own_anchors() -> set[str]:
    """Flat set of all own_anchors across every region (normalized lowercase)."""
    with open(config.REGIONS_YAML) as f:
        regions = yaml.safe_load(f)["regions"]
    anchors = set()
    for rk, region in regions.items():
        for a in region["own_anchors"]:
            anchors.add(a.lower().strip())
    return anchors

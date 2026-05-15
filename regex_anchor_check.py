from __future__ import annotations
"""
Stage 5: Regex Anchor Check
Fast first pass before touching the LLM.

For each term in ad group of region R:
  - Own anchors  (R.own_anchors)     → standalone/substring match → KEEP
  - Sibling anchors (R.sibling_anchors) → standalone/substring match → NEGATE_AG
  - No match                          → PASS (send to LLM)

sibling_anchors currently come from the active vertical targets file.

"Whole-word" = anchor surrounded by \b after lowercasing.
Multi-word anchors (e.g. "chiang mai") are matched with \b on the outer edges only.
Substring matching is a fallback for concatenated single-token dating forms.
"""

import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(__file__))
import target_loader


def _normalize(text: str) -> str:
    """Lowercase + strip accents so 'español' matches 'espanol'."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")


def load_anchor_universe() -> dict:
    """
    Returns compiled standalone and substring anchor structures by region.
    """
    return target_loader.load_anchor_patterns()


def _find_match(term: str, compiled: list[tuple[str, re.Pattern]]) -> str | None:
    term_norm = _normalize(term)
    for anchor, pattern in compiled:
        if pattern.search(term_norm):
            return anchor
    return None


def _find_substring_match(term: str, anchors: list[dict]) -> tuple[str, str] | None:
    tokens = _normalize(term).split()
    for token in tokens:
        for anchor in anchors:
            anchor_text = anchor["anchor"]
            if token == anchor_text:
                continue
            if token in anchor["excluded_tokens"]:
                continue
            if anchor_text in token:
                return anchor_text, token
    return None


def _mark_keep(
    t: dict,
    anchor: str,
    match_type: str,
    containing_token: str | None = None,
) -> None:
    t["regex_result"] = "KEEP"
    t["regex_anchor"] = anchor
    t["regex_match_type"] = match_type
    t["regex_match_origin"] = "own"
    t["match_type"] = match_type
    t["matched_anchor"] = anchor
    t["match_origin"] = "own"
    if containing_token is not None:
        t["regex_containing_token"] = containing_token
        t["containing_token"] = containing_token
    t["decision"] = "KEEP"
    t["confidence"] = "high"
    t["source"] = "regex"
    t["target_scope"] = "none"
    t["anchor_found"] = anchor
    t["reason"] = f"own anchor '{anchor}' found — correctly targeted"


def _mark_negate_ag(
    t: dict,
    anchor: str,
    match_type: str,
    containing_token: str | None = None,
) -> None:
    t["regex_result"] = "NEGATE_AG"
    t["regex_anchor"] = anchor
    t["regex_match_type"] = match_type
    t["regex_match_origin"] = "sibling"
    t["match_type"] = match_type
    t["matched_anchor"] = anchor
    t["match_origin"] = "sibling"
    if containing_token is not None:
        t["regex_containing_token"] = containing_token
        t["containing_token"] = containing_token
    t["decision"] = "NEGATE"
    t["confidence"] = "high"
    t["source"] = "regex"
    t["target_scope"] = "ad_group"
    t["anchor_found"] = anchor
    t["reason"] = f"sibling anchor '{anchor}' found — wrong ad group"


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

        own_match = _find_match(term, region_data["own"])
        if own_match:
            _mark_keep(t, own_match, "standalone")
            regex_decided.append(t)
            keep_count += 1
            continue

        sibling_match = _find_match(term, region_data["sibling"])
        if sibling_match:
            _mark_negate_ag(t, sibling_match, "standalone")
            regex_decided.append(t)
            negate_ag_count += 1
            continue

        if region_data.get("concatenation_enabled", True):
            own_substring_match = _find_substring_match(term, region_data["own_substring"])
            if own_substring_match:
                anchor, containing_token = own_substring_match
                _mark_keep(t, anchor, "substring", containing_token)
                regex_decided.append(t)
                keep_count += 1
                continue

            sibling_substring_match = _find_substring_match(term, region_data["sibling_substring"])
            if sibling_substring_match:
                anchor, containing_token = sibling_substring_match
                _mark_negate_ag(t, anchor, "substring", containing_token)
                regex_decided.append(t)
                negate_ag_count += 1
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
    """Flat set of all own_anchors across every target."""
    return target_loader.get_all_own_anchors()

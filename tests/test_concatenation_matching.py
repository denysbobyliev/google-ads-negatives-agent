from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import regex_anchor_check
import target_loader


def _policy(enabled: bool = True, min_anchor_length: int = 4, exclude_within: dict | None = None) -> dict:
    return {
        "concatenation": {
            "enabled": enabled,
            "min_anchor_length": min_anchor_length,
            "exclude_within": exclude_within or {},
        }
    }


def _classify(
    term: str,
    own_anchors: list[str],
    sibling_anchors: list[str] | None = None,
    policy: dict | None = None,
) -> dict | None:
    policy = policy or _policy()
    own_standalone, own_substring = target_loader.compile_anchor_patterns(own_anchors, policy)
    sibling_standalone, sibling_substring = target_loader.compile_anchor_patterns(
        sibling_anchors or [],
        policy,
    )
    universe = {
        "test": {
            "own": own_standalone,
            "own_substring": own_substring,
            "sibling": sibling_standalone,
            "sibling_substring": sibling_substring,
            "concatenation_enabled": policy.get("concatenation", {}).get("enabled", True),
        }
    }
    terms = [{"region_key": "test", "term": term}]
    with patch.object(regex_anchor_check, "load_anchor_universe", return_value=universe):
        llm_candidates, regex_decided = regex_anchor_check.run(terms)
    if regex_decided:
        return regex_decided[0]
    if llm_candidates:
        return None
    raise AssertionError("Term was neither decided nor passed to LLM")


class ConcatenationMatchingTests(unittest.TestCase):
    def test_substring_own_anchor_matches_korean(self) -> None:
        result = _classify("koreandating", ["korean"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")
        self.assertEqual(result["containing_token"], "koreandating")

    def test_substring_own_anchor_matches_japan(self) -> None:
        result = _classify("japandates review", ["japan"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")
        self.assertEqual(result["containing_token"], "japandates")

    def test_substring_own_anchor_matches_ukraine(self) -> None:
        result = _classify("ukrainecharm", ["ukraine"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")

    def test_substring_own_anchor_matches_latina(self) -> None:
        result = _classify("latinasingles", ["latina"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")

    def test_standalone_takes_precedence_over_substring(self) -> None:
        result = _classify("korean women", ["korean"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "standalone")
        self.assertNotIn("containing_token", result)

    def test_substring_sibling_anchor_matches(self) -> None:
        result = _classify("russiandating", ["ukraine"], ["russian"])
        self.assertEqual(result["decision"], "NEGATE")
        self.assertEqual(result["regex_result"], "NEGATE_AG")
        self.assertEqual(result["match_type"], "substring")
        self.assertEqual(result["match_origin"], "sibling")

    def test_excluded_token_falls_through(self) -> None:
        result = _classify(
            "caucasian women",
            ["asian"],
            policy=_policy(exclude_within={"asian": ["caucasian"]}),
        )
        self.assertIsNone(result)

    def test_empty_excluded_token_keeps_unsafe_substring(self) -> None:
        result = _classify("caucasian women", ["asian"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")

    def test_short_anchor_is_not_substring_matched(self) -> None:
        result = _classify("ukdating site", ["uk"], policy=_policy(min_anchor_length=4))
        self.assertIsNone(result)

    def test_min_length_four_anchor_is_substring_matched(self) -> None:
        result = _classify("thaicupid", ["thai"], policy=_policy(min_anchor_length=4))
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["match_type"], "substring")

    def test_feature_flag_off_disables_substring_matching(self) -> None:
        result = _classify("koreandating", ["korean"], policy=_policy(enabled=False))
        self.assertIsNone(result)

    def test_substring_anchor_ordering_is_preserved(self) -> None:
        result = _classify("japanesedating", ["japan", "japanese"])
        self.assertEqual(result["decision"], "KEEP")
        self.assertEqual(result["matched_anchor"], "japan")

    def test_no_match_falls_through_with_feature_on_and_off(self) -> None:
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                result = _classify("dating site", ["korean"], policy=_policy(enabled=enabled))
                self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

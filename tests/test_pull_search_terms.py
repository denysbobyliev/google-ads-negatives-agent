from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pull_search_terms


class PullSearchTermsTests(unittest.TestCase):
    def test_chunked_splits_ids(self) -> None:
        self.assertEqual(
            pull_search_terms._chunked(["1", "2", "3"], 2),
            [["1", "2"], ["3"]],
        )

    def test_merge_raw_combines_same_ad_group_term_metrics(self) -> None:
        target = {
            ("1", "thai dating"): {
                "term": "thai dating",
                "ad_group_id": "1",
                "clicks": 1,
                "cost": 2.5,
                "conversions": 0.0,
                "conversions_value": 0.0,
            }
        }
        source = {
            ("1", "thai dating"): {
                "term": "thai dating",
                "ad_group_id": "1",
                "clicks": 2,
                "cost": 1.5,
                "conversions": 1.0,
                "conversions_value": 50.0,
            },
            ("2", "asian dating"): {
                "term": "asian dating",
                "ad_group_id": "2",
                "clicks": 3,
                "cost": 4.0,
                "conversions": 0.0,
                "conversions_value": 0.0,
            },
        }

        pull_search_terms._merge_raw(target, source)

        self.assertEqual(target[("1", "thai dating")]["clicks"], 3)
        self.assertEqual(target[("1", "thai dating")]["cost"], 4.0)
        self.assertEqual(target[("1", "thai dating")]["conversions"], 1.0)
        self.assertEqual(target[("1", "thai dating")]["conversions_value"], 50.0)
        self.assertIn(("2", "asian dating"), target)


if __name__ == "__main__":
    unittest.main()

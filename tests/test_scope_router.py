from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import scope_router


class ScopeRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "Asia": "Asia-Search",
            "Japan": "Asia-Search",
            "Germany": "Euro-Search",
            "Europe": "Euro-Search",
            "Latina": "Latin-Search",
            "Mexico": "Latin-Search",
        }

    def test_plain_route_keeps_only_matching_ad_group(self) -> None:
        self.assertEqual(scope_router.resolve("Japan", "Japan", self.inventory), "KEEP")
        self.assertEqual(scope_router.resolve("Japan", "Asia", self.inventory), "NEGATE")

    def test_route_alias_keeps_renamed_ad_group(self) -> None:
        inventory = {**self.inventory, "Eastern/Oriental": "Asia-Search"}
        cfg = {"route_aliases": {"Eastern": "Eastern/Oriental"}}
        self.assertEqual(
            scope_router.route_to_action("Eastern", "Eastern/Oriental", inventory, cfg),
            "KEEP",
        )
        self.assertEqual(
            scope_router.route_to_action("Eastern", "Japan", inventory, cfg),
            "NEGATE",
        )

    def test_campaign_protect_keeps_campaign_zone(self) -> None:
        self.assertEqual(
            scope_router.resolve("CAMPAIGN_PROTECT:Asia-Search", "Japan", self.inventory),
            "KEEP",
        )
        self.assertEqual(
            scope_router.resolve("CAMPAIGN_PROTECT:Asia-Search", "Germany", self.inventory),
            "NEGATE",
        )

    def test_language_keep_expands_to_member_countries_and_generals(self) -> None:
        self.assertEqual(scope_router.resolve("LANG_KEEP:de", "Germany", self.inventory), "KEEP")
        self.assertEqual(scope_router.resolve("LANG_KEEP:de", "Europe", self.inventory), "KEEP")
        self.assertEqual(scope_router.resolve("LANG_KEEP:de", "Mexico", self.inventory), "NEGATE")

    def test_review_is_noop_and_negate_all_is_negate(self) -> None:
        self.assertEqual(scope_router.resolve("REVIEW", "Japan", self.inventory), "NOOP")
        self.assertEqual(scope_router.resolve("NEGATE_ALL", "Japan", self.inventory), "NEGATE")

    def test_force_keep_in_overrides_route(self) -> None:
        self.assertEqual(
            scope_router.resolve(
                "Russia",
                "Thailand",
                {**self.inventory, "Thailand": "Asia-Search", "Russia": "Slavic-Search"},
                {"force_keep_in": "Thailand"},
            ),
            "KEEP",
        )


if __name__ == "__main__":
    unittest.main()

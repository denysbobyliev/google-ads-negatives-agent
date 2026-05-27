from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import guards
import scope_router
import vertical_loader


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "Asia": "Asia-Search",
            "China": "Asia-Search",
            "Denmark": "Euro-Search",
            "Filipina": "Asia-Search",
            "Germany": "Euro-Search",
            "India": "Asia-Search",
            "Indonesia": "Asia-Search",
            "Ireland": "Euro-Search",
            "Japan": "Asia-Search",
            "Jamaica": "Latin-Search",
            "Korea": "Asia-Search",
            "Portugal": "Euro-Search",
            "Russia": "Slavic-Search",
            "Spain": "Euro-Search",
            "Thailand": "Asia-Search",
            "Ukraine": "Slavic-Search",
        }
        self.idx = vertical_loader.build_anchor_index(self.inventory)
        self.resolve_action = scope_router.make_resolver(self.inventory)

    def apply_one(self, row: dict) -> dict:
        return guards.run_guards(dict(row), self.inventory, self.idx, self.resolve_action)

    def test_guard1_is_telemetry_not_route_rewrite(self) -> None:
        result = self.apply_one(
            {
                "term": "danish dating site",
                "ad_group_name": "Denmark",
                "route": "Scandinavia",
                "confidence": 0.88,
            }
        )

        self.assertEqual(result["route"], "Scandinavia")
        self.assertIn("GUARD1/telemetry", result["flag"])

    def test_served_anchor_detector_catches_inventory_country_and_city(self) -> None:
        self.assertTrue(
            vertical_loader.served_anchor_in_term("China", "best chinese dating app uk", self.idx)
        )
        self.assertTrue(vertical_loader.served_anchor_in_term("Ireland", "dublin dating", self.idx))
        self.assertTrue(vertical_loader.served_anchor_in_term("Spain", "barcelona dating", self.idx))
        self.assertTrue(vertical_loader.served_anchor_in_term("India", "desi dating", self.idx))
        self.assertTrue(vertical_loader.served_anchor_in_term("Portugal", "girls in portugal", self.idx))
        # This is an accepted over-flag in the integration package: it costs a
        # Sonnet escalation, then the doctrine still negates it as no target India.
        self.assertTrue(
            vertical_loader.served_anchor_in_term(
                "India",
                "native american indian dating sites",
                self.idx,
            )
        )

    def test_fused_country_anchor_detector_uses_inventory(self) -> None:
        self.assertTrue(vertical_loader.served_anchor_in_term("Ukraine", "ukrainecharm review", self.idx))
        self.assertTrue(vertical_loader.served_anchor_in_term("Korea", "koreadates review", self.idx))
        self.assertFalse(vertical_loader.served_anchor_in_term("Korea", "koreanwar documentary", self.idx))

    def test_new_business_reversals_are_geo_anchors(self) -> None:
        self.assertTrue(
            vertical_loader.served_anchor_in_term("Scandinavia", "viking dating sites", self.idx)
        )
        self.assertTrue(vertical_loader.served_anchor_in_term("Italy", "bumble italia", self.idx))
        self.assertTrue(vertical_loader.served_anchor_in_term("Jamaica", "jamaica dating site", self.idx))

    def test_chispa_protects_latin_campaign(self) -> None:
        result = self.apply_one(
            {
                "term": "chispa app",
                "ad_group_name": "Latina",
                "route": "NEGATE_ALL",
                "level": "none",
                "confidence": 0.75,
            }
        )

        self.assertEqual(result["route"], "CAMPAIGN_PROTECT:Latin-Search")
        self.assertIn("GUARD4", result["flag"])

    def test_dual_anchor_sets_force_keep_only_when_action_would_negate(self) -> None:
        result = self.apply_one(
            {
                "term": "russian women in phuket",
                "ad_group_name": "Thailand",
                "route": "Russia",
                "confidence": 0.82,
            }
        )

        self.assertEqual(result["route"], "Russia")
        self.assertEqual(result["force_keep_in"], "Thailand")
        self.assertIn("GUARD2", result["flag"])

    def test_single_own_anchor_does_not_force_keep(self) -> None:
        result = self.apply_one(
            {
                "term": "asian dating app",
                "ad_group_name": "Asia",
                "route": "NEGATE_ALL",
                "confidence": 0.90,
            }
        )

        self.assertNotIn("force_keep_in", result)
        self.assertEqual(result["route"], "NEGATE_ALL")
        self.assertIn("GUARD1/telemetry", result["flag"])

    def test_receptivity_framing_restores_partner_route(self) -> None:
        result = self.apply_one(
            {
                "term": "german women looking for american men",
                "ad_group_name": "Germany",
                "route": "NEGATE_ALL",
                "confidence": 0.88,
                "reason": "Wrong audience: women looking for American men.",
            }
        )

        self.assertEqual(result["route"], "Germany")
        self.assertIn("GUARD3", result["flag"])

    def test_coined_brand_level_normalizes_to_source(self) -> None:
        rows = [
            {
                "term": "sakuradate review",
                "ad_group_name": "Asia",
                "route": "CAMPAIGN_PROTECT:Asia-Search",
                "level": "brand_compound",
                "confidence": 0.74,
            },
            {
                "term": "www orchidromance com",
                "ad_group_name": "Asia",
                "route": "NEGATE_ALL",
                "level": "brand_compound",
                "confidence": 0.80,
            },
        ]

        results = [self.apply_one(row) for row in rows]

        self.assertEqual(
            [row["route"] for row in results],
            ["CAMPAIGN_PROTECT:source", "CAMPAIGN_PROTECT:source"],
        )
        self.assertTrue(all("GUARD4" in row["flag"] for row in results))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import classify_batch
import config


class PromptRenderingTests(unittest.TestCase):
    def test_system_block_uses_classifier_doctrine_and_inventory(self) -> None:
        config.apply_account_profile(config.DEFAULT_ACCOUNT_PROFILE)
        system = classify_batch.build_system_block("Japan\tAsia-Search")

        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertIn("Dating Geo Negative-Keyword Classifier", system[0]["text"])
        self.assertIn("ACCOUNT BLOCK", system[0]["text"])
        self.assertIn("## Live ad-group inventory", system[0]["text"])
        self.assertIn("Japan\tAsia-Search", system[0]["text"])

    def test_account_block_is_parsed_from_classifier_prompt(self) -> None:
        cfg = config.load_account_config()

        self.assertEqual(cfg["generals"]["Asia-Search"], "Asia")
        self.assertIn("es", cfg["language_map"])
        self.assertEqual(cfg["special_cases"]["eastern_european"], "Slavic")

    def test_parse_json_array_strips_markdown_fences(self) -> None:
        parsed = classify_batch.parse_json_array(
            '```json\n[{"term":"x","route":"NEGATE_ALL"}]\n```'
        )

        self.assertEqual(parsed[0]["route"], "NEGATE_ALL")


if __name__ == "__main__":
    unittest.main()

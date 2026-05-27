from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import dedupe_cache
import update_cache


class CacheBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_values = {
            "ACCOUNT_KEY": config.ACCOUNT_KEY,
            "VERTICAL_KEY": config.VERTICAL_KEY,
            "POLICY_VERSION": config.POLICY_VERSION,
            "PROMPT_VERSION": config.PROMPT_VERSION,
            "DATA_DIR": config.DATA_DIR,
            "CLASSIFIED_TERMS_PATH": config.CLASSIFIED_TERMS_PATH,
        }
        config.ACCOUNT_KEY = "account_a"
        config.VERTICAL_KEY = "vertical_a"
        config.POLICY_VERSION = "policy_a"
        config.PROMPT_VERSION = "prompt_a"
        config.DATA_DIR = self.tmp.name
        config.CLASSIFIED_TERMS_PATH = os.path.join(self.tmp.name, "classified_terms.json")

    def tearDown(self) -> None:
        for key, value in self.old_values.items():
            setattr(config, key, value)
        self.tmp.cleanup()

    def test_dedupe_accepts_legacy_cache_entries(self) -> None:
        with open(config.CLASSIFIED_TERMS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"ad_group_name": "Ukraine", "term": "ukrainian dating"}], f)

        fresh = dedupe_cache.run([
            {"ad_group_name": "Ukraine", "term": "ukrainian dating"},
            {"ad_group_name": "Poland", "term": "polish dating"},
        ])

        self.assertEqual([t["term"] for t in fresh], ["polish dating"])

    def test_update_cache_writes_profile_metadata(self) -> None:
        update_cache.run([
            {
                "ad_group_name": "Ukraine",
                "campaign_name": "Slavic-Search",
                "term": "ukrainian dating",
                "decision": "KEEP",
                "confidence": "high",
                "source": "haiku",
            }
        ])

        with open(config.CLASSIFIED_TERMS_PATH, encoding="utf-8") as f:
            entries = json.load(f)

        self.assertEqual(entries[0]["account_key"], "account_a")
        self.assertEqual(entries[0]["vertical_key"], "vertical_a")
        self.assertEqual(entries[0]["policy_version"], "policy_a")
        self.assertEqual(entries[0]["prompt_version"], "prompt_a")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


class ConfigProfileTests(unittest.TestCase):
    def tearDown(self) -> None:
        config.apply_account_profile(config.DEFAULT_ACCOUNT_PROFILE)

    def test_apply_account_profile_sets_account_labels_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = os.path.join(tmp, "profile.yaml")
            with open(profile_path, "w", encoding="utf-8") as f:
                f.write(textwrap.dedent("""
                    account_key: test_account
                    vertical_key: test_vertical
                    policy_version: p2
                    prompt_version: prompt3
                    customer_id: "123-456"
                    google_ads_yaml: creds/google-ads.yaml
                    policy_yaml: policy.yaml
                    prompt_template: prompt.md
                    labels:
                      master: negatives_master
                    paths:
                      data_dir: tmp-data
                      logs_dir: tmp-logs
                      reports_dir: tmp-reports
                      classified_terms: tmp-data/cache.json
                """))

            config.apply_account_profile(profile_path)

            self.assertEqual(config.ACCOUNT_KEY, "test_account")
            self.assertEqual(config.VERTICAL_KEY, "test_vertical")
            self.assertEqual(config.POLICY_VERSION, "p2")
            self.assertEqual(config.PROMPT_VERSION, "prompt3")
            self.assertEqual(config.CUSTOMER_ID, "123456")
            self.assertEqual(config.MASTER_LABEL, "negatives_master")
            self.assertTrue(config.GOOGLE_ADS_YAML.endswith("creds/google-ads.yaml"))
            self.assertTrue(config.CLASSIFIED_TERMS_PATH.endswith("tmp-data/cache.json"))
            self.assertTrue(config.POLICY_YAML.endswith("policy.yaml"))
            self.assertTrue(config.PROMPT_TEMPLATE_PATH.endswith("prompt.md"))

    def test_default_policy_is_loaded_from_vertical_file(self) -> None:
        config.apply_account_profile(config.DEFAULT_ACCOUNT_PROFILE)

        self.assertEqual(config.COST_THRESHOLD, 3.0)
        self.assertEqual(config.CV_PROTECTION_THRESHOLD, 100.0)
        self.assertEqual(config.SCORE_THRESHOLD, 6)
        self.assertEqual(config.MAX_AG_NEGATIVES_PER_RUN, 20)
        self.assertEqual(config.HAIKU_MODEL, "claude-haiku-4-5")
        self.assertEqual(config.SONNET_MODEL, "claude-sonnet-4-6")


if __name__ == "__main__":
    unittest.main()

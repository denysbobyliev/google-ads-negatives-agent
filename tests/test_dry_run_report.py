from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import dry_run_report


class DryRunReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_values = {
            "ACCOUNT_KEY": config.ACCOUNT_KEY,
            "VERTICAL_KEY": config.VERTICAL_KEY,
            "POLICY_VERSION": config.POLICY_VERSION,
            "PROMPT_VERSION": config.PROMPT_VERSION,
            "REPORTS_DIR": config.REPORTS_DIR,
        }
        config.ACCOUNT_KEY = "account_a"
        config.VERTICAL_KEY = "vertical_a"
        config.POLICY_VERSION = "policy_a"
        config.PROMPT_VERSION = "prompt_a"
        config.REPORTS_DIR = self.tmp.name

    def tearDown(self) -> None:
        for key, value in self.old_values.items():
            setattr(config, key, value)
        self.tmp.cleanup()

    def test_report_includes_profile_metadata(self) -> None:
        path = dry_run_report.run([
            {
                "term": "ukrainian dating",
                "decision": "KEEP",
                "ad_group_name": "Ukraine",
            }
        ])

        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(rows[0]["account_key"], "account_a")
        self.assertEqual(rows[0]["vertical_key"], "vertical_a")
        self.assertEqual(rows[0]["policy_version"], "policy_a")
        self.assertEqual(rows[0]["prompt_version"], "prompt_a")


if __name__ == "__main__":
    unittest.main()

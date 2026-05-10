from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import target_loader


class TargetLoaderTests(unittest.TestCase):
    def test_default_targets_load_from_vertical_file(self) -> None:
        config.apply_account_profile(config.DEFAULT_ACCOUNT_PROFILE)

        targets = target_loader.load_targets()

        self.assertIn("ukraine", targets)
        self.assertIn("own_anchors", targets["ukraine"])
        self.assertTrue(config.TARGETS_YAML.endswith("verticals/dating_geo/targets.yaml"))


if __name__ == "__main__":
    unittest.main()

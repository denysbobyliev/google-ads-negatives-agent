from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import escalate


class EscalateMessageTests(unittest.TestCase):
    def test_row_escalation_message_includes_served_context(self) -> None:
        message = escalate.build_row_escalation_message(
            [
                {
                    "term": "is koreadates a legit website",
                    "ad_group_name": "Asia",
                    "campaign_name": "Asia-Search",
                    "route": "Korea",
                    "action": "NEGATE",
                    "reason": "Korea anchor with dates suffix.",
                }
            ]
        )

        self.assertIn("served_ad_group='Asia'", message)
        self.assertIn("served_campaign='Asia-Search'", message)
        self.assertIn("route it to that served_ad_group", message)


if __name__ == "__main__":
    unittest.main()

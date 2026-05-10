from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import llm_classify_batch


class PromptRenderingTests(unittest.TestCase):
    def test_system_prompt_uses_external_template_and_policy_threshold(self) -> None:
        config.apply_account_profile(config.DEFAULT_ACCOUNT_PROFILE)
        prompt = llm_classify_batch._build_system_prompt(
            {
                "target_region_label": "Ukraine / Ukrainian",
                "archetype": "hero_country",
                "own_anchors": ["ukraine", "ukrainian"],
                "sibling_anchors": ["poland", "polish"],
            },
            {"ukraine", "poland"},
        )

        self.assertIn("Ukraine / Ukrainian", prompt)
        self.assertIn("SINGLE-COUNTRY ad group", prompt)
        self.assertIn("Score >= 6 means KEEP", prompt)
        self.assertIn("ukraine, ukrainian", prompt)
        self.assertIn("poland, polish", prompt)
        self.assertIn("poland, ukraine", prompt)

    def test_build_system_blocks_marks_reusable_context_cacheable(self) -> None:
        config.LLM_PROMPT_CACHE_ENABLED = True
        system = llm_classify_batch._build_system_blocks(
            {
                "target_region_label": "Ukraine / Ukrainian",
                "archetype": "hero_country",
            },
            {"ukraine", "poland"},
        )

        self.assertIsInstance(system, list)
        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("CLASSIFIER DOCTRINE", system[0]["text"])
        self.assertIn("Dating Geo Classifier Doctrine", system[0]["text"])
        self.assertNotIn("TARGET DEFINITIONS", system[0]["text"])
        self.assertIn("Ukraine / Ukrainian", system[1]["text"])

    def test_call_llm_passes_system_blocks_through(self) -> None:
        system = [{"type": "text", "text": "cached", "cache_control": {"type": "ephemeral"}}]

        class FakeMessages:
            def __init__(self) -> None:
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace()

        fake_messages = FakeMessages()
        fake_client = SimpleNamespace(messages=fake_messages)

        llm_classify_batch._call_llm(
            fake_client,
            system,
            [{"role": "user", "content": "Classify:\nterm"}],
        )

        self.assertEqual(fake_messages.kwargs["system"], system)

    def test_usage_tokens_reads_prompt_cache_fields(self) -> None:
        msg = SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=20,
                cache_creation_input_tokens=30,
                cache_read_input_tokens=40,
            )
        )

        usage = llm_classify_batch._usage_tokens(msg)

        self.assertEqual(usage["input_tokens"], 10)
        self.assertEqual(usage["output_tokens"], 20)
        self.assertEqual(usage["cache_creation_input_tokens"], 30)
        self.assertEqual(usage["cache_read_input_tokens"], 40)


if __name__ == "__main__":
    unittest.main()

"""
agents_common.py — shared by classify_batch (Haiku) and escalate (Sonnet).

One doctrine source, two callers. The cached system block = classifier.md (doctrine +
ACCOUNT BLOCK) with the live inventory appended before the cache breakpoint. cache_control
goes on the single system block (Haiku 4.5 needs a >=4096-token cached prefix; the doctrine
is ~11K, so it clears). Caches are model- and workspace-scoped, so Haiku and Sonnet hold
separate entries off the identical text — expected.
"""
import json, re, os
import anthropic

client = anthropic.Anthropic()

DOCTRINE_PATH = os.environ.get("CLASSIFIER_MD", "verticals/dating_geo/prompts/classifier.md")


def load_doctrine(path=None):
    with open(path or DOCTRINE_PATH, encoding="utf-8") as f:
        return f.read()


def system_block(inventory_text, path=None):
    """Single cached system block: doctrine + injected live inventory. 1h TTL is worth the
    higher write cost when a run spans many batches."""
    text = load_doctrine(path) + "\n\n## Live ad-group inventory\n" + inventory_text
    return [{"type": "text", "text": text,
             "cache_control": {"type": "ephemeral", "ttl": "1h"}}]


def parse_json_array(text):
    """Tolerant parse: strip stray fences/prose, isolate the [ ... ] array, json.loads."""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    i, j = s.find("["), s.rfind("]")
    if i != -1 and j != -1 and j > i:
        s = s[i:j + 1]
    return json.loads(s)


def review_fallback(terms, reason="parse/api failure -> safe no-op keep"):
    return [{"term": t, "route": "REVIEW", "level": "none", "confidence": 0.0,
             "lang": None, "reason": reason} for t in terms]

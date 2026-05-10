from __future__ import annotations
"""
Stage 6: LLM Classification
Groups PASS terms by region, batches them, calls Claude, parses JSON.
Prompt and archetype text live under verticals/<vertical>/prompts/.
"""

import json
import os
import sys
import time

import anthropic
import yaml

sys.path.insert(0, os.path.dirname(__file__))
import config
from llm_logger import log_llm_failure
import target_loader

RETRY_REMINDER = (
    "Your previous response could not be parsed as JSON. "
    "Return ONLY a valid JSON array - no preamble, no markdown, no commentary."
)


def _empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key in total:
        total[key] += usage.get(key, 0)


def _load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_archetypes() -> dict[str, str]:
    with open(config.ARCHETYPES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_archetype_context(region: dict) -> str:
    archetypes = _load_archetypes()
    archetype = region.get("archetype", "hero_country")
    template = archetypes.get(archetype) or archetypes.get("hero_country", "")
    return template.format(target_region_label=region["target_region_label"])


def _build_system_prompt(region: dict, all_anchors: set[str]) -> str:
    all_anchor_str = ", ".join(sorted(all_anchors)) if all_anchors else "(none)"
    own_anchor_str = ", ".join(region.get("own_anchors", [])) or "(none)"
    sibling_anchor_str = ", ".join(region.get("sibling_anchors", [])) or "(none)"
    notes = region.get("region_notes", "")
    region_notes_block = f"NOTE: {notes}\n" if notes else ""
    template = _load_text(config.REGION_CONTEXT_TEMPLATE_PATH)
    return template.format(
        target_region_label=region["target_region_label"],
        archetype_context=_build_archetype_context(region),
        region_notes=region_notes_block,
        own_anchors_joined=own_anchor_str,
        sibling_anchors_joined=sibling_anchor_str,
        all_anchor_universe_joined=all_anchor_str,
        score_threshold=config.SCORE_THRESHOLD,
    )


def _build_cache_context() -> str:
    return (
        "Reusable vertical classifier context. This block is identical across "
        "all batches for the active vertical and is safe to cache.\n\n"
        "--- CLASSIFIER DOCTRINE ---\n"
        f"{_load_text(config.PROMPT_TEMPLATE_PATH)}\n\n"
        "--- ARCHETYPES ---\n"
        f"{yaml.safe_dump(_load_archetypes(), sort_keys=True, allow_unicode=True)}"
    )


def _build_system_blocks(region: dict, all_anchors: set[str]) -> str | list[dict]:
    rendered_prompt = _build_system_prompt(region, all_anchors)
    if not config.LLM_PROMPT_CACHE_ENABLED:
        return rendered_prompt
    return [
        {
            "type": "text",
            "text": _build_cache_context(),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": rendered_prompt,
        },
    ]


def _call_llm(
    client: anthropic.Anthropic,
    system: str | list[dict],
    messages: list[dict],
) -> anthropic.Message:
    return client.messages.create(
        model=config.MODEL,
        max_tokens=4096,
        system=system,
        messages=messages,
    )


def _parse_response(text: str) -> list[dict] | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None


def _usage_tokens(msg: anthropic.Message) -> dict[str, int]:
    usage = getattr(msg, "usage", None)
    if usage is None:
        return _empty_usage()
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        ),
        "cache_read_input_tokens": int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        ),
    }


def _classify_batch(
    client: anthropic.Anthropic,
    region: dict,
    batch_terms: list[str],
    all_anchors: set[str],
) -> tuple[list[dict], list[str], int, dict[str, int]]:
    """
    Returns (classified_objects, failed_terms, calls, usage).
    """
    system = _build_system_blocks(region, all_anchors)
    user_msg = "Classify:\n" + "\n".join(batch_terms)

    calls = 0
    usage_total = _empty_usage()

    msg = _call_llm(client, system, [{"role": "user", "content": user_msg}])
    calls += 1
    _add_usage(usage_total, _usage_tokens(msg))
    response_text = msg.content[0].text
    result = _parse_response(response_text)

    if result is None:
        retry_messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": response_text},
            {"role": "user", "content": RETRY_REMINDER},
        ]
        msg2 = _call_llm(client, system, retry_messages)
        calls += 1
        _add_usage(usage_total, _usage_tokens(msg2))
        result = _parse_response(msg2.content[0].text)

    if result is None:
        return [], batch_terms, calls, usage_total

    result_map = {
        str(r.get("term", "")).lower().strip(): r
        for r in result
        if isinstance(r, dict)
    }
    classified = []
    failed = []
    for term in batch_terms:
        if term in result_map:
            classified.append(result_map[term])
        else:
            failed.append(term)

    return classified, failed, calls, usage_total


def _load_regions_by_key() -> dict[str, dict]:
    return target_loader.load_targets()


def run(
    llm_candidates: list[dict],
    all_anchors: set[str],
) -> tuple[list[dict], int, float]:
    """
    Returns (classified_terms, llm_calls_made, estimated_cost_usd).
    """
    t0 = time.time()
    if not llm_candidates:
        print("Stage 6 — llm_classify_batch: 0 terms, skipped")
        return [], 0, 0.0

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    regions_by_key = _load_regions_by_key()

    candidates_by_region: dict[str, list[dict]] = {}
    for t in llm_candidates:
        candidates_by_region.setdefault(t["region_key"], []).append(t)

    total_calls = 0
    total_usage = _empty_usage()
    classified_count = 0
    failed_count = 0

    for rk, cands in candidates_by_region.items():
        region = regions_by_key[rk]
        terms_for_region = sorted({c["term"] for c in cands})

        by_term: dict[str, list[dict]] = {}
        for cand in cands:
            by_term.setdefault(cand["term"], []).append(cand)

        for i in range(0, len(terms_for_region), config.LLM_BATCH_SIZE):
            batch = terms_for_region[i : i + config.LLM_BATCH_SIZE]
            classified, failed, calls, usage = _classify_batch(
                client, region, batch, all_anchors
            )
            total_calls += calls
            _add_usage(total_usage, usage)

            for term in failed:
                log_llm_failure(term, rk)
                failed_count += 1

            for obj in classified:
                term = str(obj.get("term", "")).lower().strip()
                for t in by_term.get(term, []):
                    t["llm_score"] = int(obj.get("score", config.SCORE_THRESHOLD))
                    t["llm_anchor"] = obj.get("anchor")
                    t["llm_reason"] = obj.get("reason", "")
                    classified_count += 1

    result = [t for t in llm_candidates if "llm_score" in t]

    estimated_cost = (
        total_usage["input_tokens"] / 1000 * config.LLM_COST_PER_1K_INPUT_TOKENS
        + total_usage["cache_creation_input_tokens"]
        / 1000
        * config.LLM_COST_PER_1K_INPUT_TOKENS
        * config.LLM_CACHE_WRITE_INPUT_MULTIPLIER
        + total_usage["cache_read_input_tokens"]
        / 1000
        * config.LLM_COST_PER_1K_INPUT_TOKENS
        * config.LLM_CACHE_READ_INPUT_MULTIPLIER
        + total_usage["output_tokens"] / 1000 * config.LLM_COST_PER_1K_OUTPUT_TOKENS
    )

    elapsed = time.time() - t0
    print(
        f"Stage 6 — llm_classify_batch: {classified_count} classified, "
        f"{failed_count} parse failures, {total_calls} API calls, "
        f"regular_input={total_usage['input_tokens']}, "
        f"cache_write={total_usage['cache_creation_input_tokens']}, "
        f"cache_read={total_usage['cache_read_input_tokens']}, "
        f"output={total_usage['output_tokens']}, "
        f"estimated_cost=${estimated_cost:.4f} "
        f"(in {elapsed:.1f}s)"
    )
    return result, total_calls, estimated_cost

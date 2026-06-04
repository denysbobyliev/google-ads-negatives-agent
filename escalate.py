from __future__ import annotations
"""
Stage 6b: Sonnet terminal escalation for low-confidence/REVIEW terms.
"""

import os
import sys
import time

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import config
from classify_batch import (
    add_usage,
    _empty_usage,
    _estimated_cost,
    _normalize_result,
    _review_result,
    _usage_tokens,
    build_system_block,
    format_usage,
    parse_json_array,
)
from llm_logger import log_llm_failure


def build_escalation_message(terms: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {term}" for i, term in enumerate(terms))
    return (
        "These terms were low-confidence on a first pass. You are the final "
        "decision-maker - there is no human review after you. Resolve each to "
        "a concrete route per the doctrine. Prefer a definite route over REVIEW; "
        "use REVIEW only if genuinely unresolvable. Return ONLY the JSON array "
        "per the Output Contract.\n\nTerms:\n"
        f"{numbered}"
    )


def build_row_escalation_message(rows: list[dict]) -> str:
    numbered = "\n".join(
        (
            f"{i + 1}. term={row.get('term', '')!r}; "
            f"served_ad_group={row.get('ad_group_name') or row.get('served_ad_group') or ''!r}; "
            f"served_campaign={row.get('campaign_name') or row.get('served_campaign') or ''!r}; "
            f"first_pass_route={row.get('route', '')!r}; "
            f"first_pass_action={row.get('action', '')!r}; "
            f"first_pass_reason={row.get('reason', '')!r}"
        )
        for i, row in enumerate(rows)
    )
    return (
        "These rows were escalated because a first pass might create a false negative. "
        "You are the final decision-maker for each served instance - there is no human "
        "review after you. Use the served_ad_group and served_campaign context. If the "
        "term is acceptable where it was found, route it to that served_ad_group. "
        "Prefer KEEP/NOOP safety over auto-negating nuanced geo, ethnic-brand, city/"
        "homonym, or community terms. Return ONLY a JSON array, one object per row in "
        "the same order, per the Output Contract. The term field must match the input "
        "term; no prose, no fences.\n\nRows:\n"
        f"{numbered}"
    )


def escalate_terms(
    terms: list[str],
    inventory_text: str,
) -> tuple[dict[str, dict], int, float, dict[str, int]]:
    unique_terms = sorted({term.lower().strip() for term in terms if term})
    if not unique_terms:
        return {}, 0, 0.0, _empty_usage()

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    usage = _empty_usage()
    predictions: dict[str, dict] = {}
    calls = 0

    for i in range(0, len(unique_terms), config.LLM_BATCH_SIZE):
        batch = unique_terms[i : i + config.LLM_BATCH_SIZE]
        msg = client.messages.create(
            model=config.SONNET_MODEL,
            max_tokens=max(512, 80 * len(batch)),
            temperature=0,
            system=build_system_block(inventory_text),
            messages=[{"role": "user", "content": build_escalation_message(batch)}],
        )
        calls += 1
        usage_part = _usage_tokens(msg)
        add_usage(usage, usage_part)

        parsed = parse_json_array(msg.content[0].text)
        if parsed is None:
            for term in batch:
                log_llm_failure(term, "sonnet")
                predictions[term] = _review_result(term)
            continue

        by_term = {
            str(obj.get("term", "")).lower().strip(): obj
            for obj in parsed
            if isinstance(obj, dict)
        }
        for term in batch:
            obj = by_term.get(term)
            if obj is None:
                log_llm_failure(term, "sonnet")
                predictions[term] = _review_result(term)
            else:
                predictions[term] = _normalize_result(obj, term)

    return predictions, calls, _estimated_cost(usage), usage


def escalate(terms: list[str], inventory_text: str) -> list[dict]:
    """Integration-harness wrapper returning a flat list without cost metadata."""
    predictions, _, _, _ = escalate_terms(terms, inventory_text)
    return [predictions.get(term.lower().strip(), _review_result(term)) for term in terms]


def _escalate_rows(
    term_rows: list[dict],
    inventory_text: str,
) -> tuple[list[dict], int, float, dict[str, int]]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    usage = _empty_usage()
    escalated: list[dict] = []
    calls = 0

    for i in range(0, len(term_rows), config.LLM_BATCH_SIZE):
        batch = term_rows[i : i + config.LLM_BATCH_SIZE]
        msg = client.messages.create(
            model=config.SONNET_MODEL,
            max_tokens=max(512, 120 * len(batch)),
            temperature=0,
            system=build_system_block(inventory_text),
            messages=[{"role": "user", "content": build_row_escalation_message(batch)}],
        )
        calls += 1
        add_usage(usage, _usage_tokens(msg))

        parsed = parse_json_array(msg.content[0].text)
        if parsed is None or len(parsed) != len(batch):
            for row in batch:
                log_llm_failure(row["term"], "sonnet_row")
                result = _review_result(row["term"])
                escalated.append({**row, **result, "source": "sonnet", "escalated": True})
            continue

        for row, obj in zip(batch, parsed):
            result = _normalize_result(obj, row["term"])
            escalated.append({**row, **result, "source": "sonnet", "escalated": True})

    return escalated, calls, _estimated_cost(usage), usage


def run(
    term_rows: list[dict],
    inventory_text: str,
) -> tuple[list[dict], int, float, dict[str, int]]:
    t0 = time.time()
    if not term_rows:
        print("Stage 6b — escalate: 0 terms, skipped")
        return [], 0, 0.0, _empty_usage()

    escalated, calls, estimated_cost, usage = _escalate_rows(term_rows, inventory_text)

    elapsed = time.time() - t0
    print(
        f"Stage 6b — escalate: {len(escalated)} rows, "
        f"{len({row['term'] for row in escalated})} unique terms, {calls} API calls, "
        f"{format_usage(usage)}, "
        f"estimated_cost=${estimated_cost:.4f} (in {elapsed:.1f}s)"
    )
    return escalated, calls, estimated_cost, usage

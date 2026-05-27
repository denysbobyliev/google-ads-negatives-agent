from __future__ import annotations
"""
Stage 5: Haiku route classification.

Classifies one route per unique search term using the shared classifier doctrine
and live ad-group inventory. Parse failures fail safe as REVIEW.
"""

import json
import os
import sys
import time
from collections.abc import Iterable

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import config
from llm_logger import log_llm_failure

RETRY_REMINDER = (
    "Your previous response could not be parsed as JSON. "
    "Return ONLY a valid JSON array - no preamble, no markdown, no commentary."
)


def _load_doctrine() -> str:
    with open(config.PROMPT_TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def build_system_block(inventory_text: str) -> list[dict]:
    return [
        {
            "type": "text",
            "text": _load_doctrine() + "\n\n## Live ad-group inventory\n" + inventory_text,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]


def build_user_message(terms: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {term}" for i, term in enumerate(terms))
    return (
        "Classify each search term below. Return ONLY a JSON array, one object "
        "per term, in input order, exactly per the Output Contract. No prose, "
        "no fences.\n\nTerms:\n"
        f"{numbered}"
    )


def parse_json_array(text: str) -> list[dict] | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    if not all(isinstance(item, dict) for item in parsed):
        return None
    return parsed


def _review_result(term: str, reason: str = "Classifier did not return a usable route.") -> dict:
    return {
        "term": term,
        "route": "REVIEW",
        "level": "none",
        "confidence": 0.0,
        "lang": None,
        "reason": reason,
    }


def _normalize_result(obj: dict, fallback_term: str) -> dict:
    term = str(obj.get("term") or fallback_term).lower().strip()
    route = str(obj.get("route") or "REVIEW").strip() or "REVIEW"
    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "term": term,
        "route": route,
        "level": obj.get("level") or "none",
        "confidence": max(0.0, min(1.0, confidence)),
        "lang": obj.get("lang"),
        "reason": obj.get("reason") or "",
    }


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


def _usage_tokens(msg) -> dict[str, int]:
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


def _estimated_cost(usage: dict[str, int]) -> float:
    return (
        usage["input_tokens"] / 1000 * config.LLM_COST_PER_1K_INPUT_TOKENS
        + usage["cache_creation_input_tokens"]
        / 1000
        * config.LLM_COST_PER_1K_INPUT_TOKENS
        * config.LLM_CACHE_WRITE_INPUT_MULTIPLIER
        + usage["cache_read_input_tokens"]
        / 1000
        * config.LLM_COST_PER_1K_INPUT_TOKENS
        * config.LLM_CACHE_READ_INPUT_MULTIPLIER
        + usage["output_tokens"] / 1000 * config.LLM_COST_PER_1K_OUTPUT_TOKENS
    )


def add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    _add_usage(total, usage)


def format_usage(usage: dict[str, int]) -> str:
    return (
        f"regular_input={usage['input_tokens']}, "
        f"cache_write={usage['cache_creation_input_tokens']}, "
        f"cache_read={usage['cache_read_input_tokens']}, "
        f"output={usage['output_tokens']}"
    )


def _chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _call_sync(
    client: anthropic.Anthropic,
    terms: list[str],
    inventory_text: str,
) -> tuple[list[dict], int, dict[str, int]]:
    system = build_system_block(inventory_text)
    user = build_user_message(terms)
    usage = _empty_usage()

    msg = client.messages.create(
        model=config.HAIKU_MODEL,
        max_tokens=max(512, 80 * len(terms)),
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    _add_usage(usage, _usage_tokens(msg))
    parsed = parse_json_array(msg.content[0].text)
    calls = 1

    if parsed is None:
        msg2 = client.messages.create(
            model=config.HAIKU_MODEL,
            max_tokens=max(512, 80 * len(terms)),
            temperature=0,
            system=system,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": msg.content[0].text},
                {"role": "user", "content": RETRY_REMINDER},
            ],
        )
        _add_usage(usage, _usage_tokens(msg2))
        parsed = parse_json_array(msg2.content[0].text)
        calls += 1

    if parsed is None:
        for term in terms:
            log_llm_failure(term, "haiku")
        return [_review_result(term) for term in terms], calls, usage

    by_term = {
        str(obj.get("term", "")).lower().strip(): obj
        for obj in parsed
        if isinstance(obj, dict)
    }
    results = []
    for term in terms:
        obj = by_term.get(term)
        if obj is None:
            log_llm_failure(term, "haiku")
            results.append(_review_result(term))
        else:
            results.append(_normalize_result(obj, term))
    return results, calls, usage


def _call_batch_api(
    client: anthropic.Anthropic,
    batches: list[list[str]],
    inventory_text: str,
) -> tuple[list[dict], int, dict[str, int]]:
    system = build_system_block(inventory_text)
    requests = []
    for i, terms in enumerate(batches):
        requests.append(
            {
                "custom_id": str(i),
                "params": {
                    "model": config.HAIKU_MODEL,
                    "max_tokens": max(512, 80 * len(terms)),
                    "temperature": 0,
                    "system": system,
                    "messages": [
                        {"role": "user", "content": build_user_message(terms)}
                    ],
                },
            }
        )

    batch = client.messages.batches.create(requests=requests)
    start = time.time()
    while getattr(batch, "processing_status", "") not in {"ended", "canceled", "expired"}:
        if time.time() - start > config.LLM_BATCH_TIMEOUT_SECONDS:
            raise TimeoutError(f"Anthropic batch {batch.id} did not finish in time")
        time.sleep(config.LLM_BATCH_POLL_SECONDS)
        batch = client.messages.batches.retrieve(batch.id)

    if getattr(batch, "processing_status", "") != "ended":
        raise RuntimeError(f"Anthropic batch {batch.id} ended as {batch.processing_status}")

    usage = _empty_usage()
    all_results: list[dict] = []
    calls = len(requests)
    terms_by_id = {str(i): terms for i, terms in enumerate(batches)}

    for item in client.messages.batches.results(batch.id):
        terms = terms_by_id.get(str(item.custom_id), [])
        result = getattr(item, "result", None)
        if getattr(result, "type", "") != "succeeded":
            for term in terms:
                log_llm_failure(term, "haiku_batch")
                all_results.append(_review_result(term))
            continue
        message = result.message
        _add_usage(usage, _usage_tokens(message))
        parsed = parse_json_array(message.content[0].text)
        if parsed is None:
            retry_results, retry_calls, retry_usage = _call_sync(client, terms, inventory_text)
            calls += retry_calls
            _add_usage(usage, retry_usage)
            all_results.extend(retry_results)
            continue
        by_term = {
            str(obj.get("term", "")).lower().strip(): obj
            for obj in parsed
            if isinstance(obj, dict)
        }
        for term in terms:
            obj = by_term.get(term)
            if obj is None:
                log_llm_failure(term, "haiku_batch")
                all_results.append(_review_result(term))
            else:
                all_results.append(_normalize_result(obj, term))

    return all_results, calls, usage


def classify_terms(
    terms: list[str],
    inventory_text: str,
    use_batch_api: bool | None = None,
) -> tuple[dict[str, dict], int, float, dict[str, int]]:
    unique_terms = sorted({term.lower().strip() for term in terms if term})
    if not unique_terms:
        return {}, 0, 0.0, _empty_usage()

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    batches = list(_chunked(unique_terms, config.LLM_BATCH_SIZE))
    use_batch = config.LLM_USE_BATCH_API if use_batch_api is None else use_batch_api

    if use_batch:
        results, calls, usage = _call_batch_api(client, batches, inventory_text)
    else:
        calls = 0
        usage = _empty_usage()
        results = []
        for batch_terms in batches:
            batch_results, batch_calls, batch_usage = _call_sync(
                client, batch_terms, inventory_text
            )
            calls += batch_calls
            _add_usage(usage, batch_usage)
            results.extend(batch_results)

    return {r["term"]: r for r in results}, calls, _estimated_cost(usage), usage


def classify_batch(terms: list[str], inventory_text: str) -> list[dict]:
    """Integration-harness wrapper returning a flat list without cost metadata."""
    predictions, _, _, _ = classify_terms(terms, inventory_text)
    return [predictions.get(term.lower().strip(), _review_result(term)) for term in terms]


def run(
    term_rows: list[dict],
    inventory_text: str,
) -> tuple[list[dict], int, float, dict[str, int]]:
    t0 = time.time()
    if not term_rows:
        print("Stage 5 — classify_batch: 0 terms, skipped")
        return [], 0, 0.0, _empty_usage()

    predictions, calls, estimated_cost, usage = classify_terms(
        [t["term"] for t in term_rows],
        inventory_text,
    )

    classified = []
    for row in term_rows:
        result = predictions.get(row["term"], _review_result(row["term"]))
        updated = {**row, **result}
        updated["source"] = "haiku"
        updated["escalated"] = False
        classified.append(updated)

    elapsed = time.time() - t0
    print(
        f"Stage 5 — classify_batch: {len(classified)} rows, "
        f"{len(predictions)} unique terms, {calls} API calls, "
        f"{format_usage(usage)}, "
        f"estimated_cost=${estimated_cost:.4f} (in {elapsed:.1f}s)"
    )
    return classified, calls, estimated_cost, usage

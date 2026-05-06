from __future__ import annotations
"""Shared structured loggers for the negatives pipeline."""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import config


def _append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def log_llm_failure(term: str, region_key: str) -> None:
    path = os.path.join(config.LOGS_DIR, "llm_failures.jsonl")
    _append_jsonl(path, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "region_key": region_key,
        "term": term,
    })


def log_upload_error(entity_type: str, entity_id: str, term: str, error: str) -> None:
    path = os.path.join(config.LOGS_DIR, "upload_errors.jsonl")
    _append_jsonl(path, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "term": term,
        "error": error,
    })

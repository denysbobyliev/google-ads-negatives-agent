from __future__ import annotations
"""
Stage 11: Update Cache
Appends every classified term (KEEP, NEGATE, PROTECTED) to
data/classified_terms.json with an atomic write (temp file → rename).
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import config


def run(all_classified: list[dict]) -> None:
    """all_classified should include KEEP, NEGATE, and PROTECTED terms."""
    t0 = time.time()

    os.makedirs(config.DATA_DIR, exist_ok=True)

    if os.path.exists(config.CLASSIFIED_TERMS_PATH):
        with open(config.CLASSIFIED_TERMS_PATH) as f:
            cache = json.load(f)
    else:
        cache = []

    ts = datetime.now(timezone.utc).isoformat()
    for t in all_classified:
        if t.get("decision") == "DEFER":
            continue
        cache.append({
            "account_key": config.ACCOUNT_KEY,
            "vertical_key": config.VERTICAL_KEY,
            "policy_version": config.POLICY_VERSION,
            "prompt_version": config.PROMPT_VERSION,
            "ad_group_name": t.get("ad_group_name"),
            "campaign_name": t.get("campaign_name"),
            "term": t.get("term"),
            "decision": t.get("decision"),
            "route": t.get("route"),
            "action": t.get("action"),
            "confidence": t.get("confidence"),
            "source": t.get("source"),
            "timestamp": ts,
        })

    dir_ = os.path.dirname(config.CLASSIFIED_TERMS_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f, indent=2)
        os.replace(tmp_path, config.CLASSIFIED_TERMS_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    elapsed = time.time() - t0
    print(
        f"Stage 11 — update_cache: {len(all_classified)} terms appended "
        f"({len(cache)} total in cache) (in {elapsed:.1f}s)"
    )

from __future__ import annotations
"""
Stage 9: Dry-Run Report
Always writes reports/run_YYYY-MM-DD_HHMMSS.csv regardless of DRY_RUN flag.
If DRY_RUN=True the pipeline stops here before any mutations are sent.
"""

import csv
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import config

COLUMNS = [
    "account_key",
    "vertical_key",
    "policy_version",
    "prompt_version",
    "term",
    "ad_group_name",
    "campaign_name",
    "route",
    "action",
    "decision",
    "score",
    "level",
    "lang",
    "anchor_found",
    "source",
    "gate",
    "escalated",
    "flag",
    "force_keep_in",
    "target_scope",
    "clicks",
    "cost",
    "conversions",
    "conversions_value",
    "reason",
]


def run(all_terms: list[dict]) -> str:
    """
    Writes the report and returns the file path.
    all_terms should be the combined flat list from every stage output.
    """
    t0 = time.time()
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(config.REPORTS_DIR, f"run_{ts}.csv")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for t in all_terms:
            row = {col: t.get(col, "") for col in COLUMNS}
            row["account_key"] = config.ACCOUNT_KEY
            row["vertical_key"] = config.VERTICAL_KEY
            row["policy_version"] = config.POLICY_VERSION
            row["prompt_version"] = config.PROMPT_VERSION
            writer.writerow(row)

    elapsed = time.time() - t0
    print(f"Stage 9 — dry_run_report: {len(all_terms)} rows → {path} (in {elapsed:.1f}s)")
    return path

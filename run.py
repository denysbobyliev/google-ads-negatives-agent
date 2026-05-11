from __future__ import annotations
"""
Negatives Pipeline Orchestrator
Chains all 11 stages. Structured logging to logs/negatives_YYYY-MM-DD.log.
Per-stage summary printed to stdout. Final cost/action summary at end.

Usage:
  python run.py [--account-profile accounts/dating_main.yaml] [--dry-run] [--days 30] [--region korea]
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import config

import pull_scope
import pull_search_terms
import filter_by_cost
import dedupe_cache
import regex_anchor_check
import llm_classify_batch
import confidence_gate
import scope_router
import dry_run_report
import upload_negatives
import update_cache


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log_file = os.path.join(
        config.LOGS_DIR,
        f"negatives_{datetime.now().strftime('%Y-%m-%d')}.log",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Ads negative keyword pipeline")
    parser.add_argument(
        "--account-profile",
        default=config.DEFAULT_ACCOUNT_PROFILE,
        help="YAML profile with customer ID, credential path, labels, and output paths",
    )
    parser.add_argument(
        "--customer-id",
        default=None,
        help="Override the customer ID from --account-profile",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=config.DRY_RUN,
        help="If set, report is generated but no mutations are sent (default: True)",
    )
    parser.add_argument("--days", type=int, default=config.DAYS)
    parser.add_argument(
        "--region",
        default=None,
        help="Run for a single region only (e.g. 'korea')",
    )
    parser.add_argument(
        "--ignore-cache",
        action="store_true",
        default=False,
        help="Skip dedupe stage — re-evaluate all terms regardless of cache (dry-run only)",
    )
    parser.add_argument(
        "--write-cache",
        action="store_true",
        default=False,
        help="Write local cache in dry-run. Live runs always update cache after upload.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    profile = config.apply_account_profile(args.account_profile)
    _setup_logging()

    # Override config from CLI
    config.DRY_RUN = args.dry_run
    config.DAYS = args.days
    customer_id = (args.customer_id or config.CUSTOMER_ID).replace("-", "")
    region_filter = args.region
    ignore_cache = args.ignore_cache
    write_cache = args.write_cache

    if not customer_id or not customer_id.isdigit():
        print(
            "ERROR: customer_id is missing or is still a placeholder. "
            "Set it in an ignored local --account-profile or pass --customer-id."
        )
        return

    if not config.MASTER_LABEL or "<" in config.MASTER_LABEL:
        print("ERROR: labels.master is missing or is still a placeholder in the account profile.")
        return

    if not config.REGION_LABEL_PREFIX or "<" in config.REGION_LABEL_PREFIX:
        print("ERROR: labels.region_prefix is missing or is still a placeholder in the account profile.")
        return

    if ignore_cache and not config.DRY_RUN:
        print("ERROR: --ignore-cache is only allowed with --dry-run.")
        return

    run_start = time.time()
    print(
        f"\n{'='*60}\n"
        f"Negatives pipeline — customer {customer_id}\n"
        f"account={config.ACCOUNT_KEY}  vertical={config.VERTICAL_KEY}\n"
        f"dry_run={config.DRY_RUN}  days={config.DAYS}  "
        f"region={region_filter or 'all'}  ignore_cache={ignore_cache}  "
        f"write_cache={write_cache}\n"
        f"{'='*60}"
    )

    # ------------------------------------------------------------------
    # Stage 1: Pull Scope
    # ------------------------------------------------------------------
    scope = pull_scope.run(customer_id, region_filter=region_filter)
    if not scope:
        print("No ad groups in scope. Check regions.yaml labels.")
        return

    # ------------------------------------------------------------------
    # Stage 2: Pull Search Terms
    # ------------------------------------------------------------------
    terms = pull_search_terms.run(customer_id, scope, days=args.days)
    if not terms:
        print("No search terms found.")
        return

    # ------------------------------------------------------------------
    # Stage 3: Filter by Cost
    # ------------------------------------------------------------------
    active_terms, protected_terms, below_threshold_terms = filter_by_cost.run(terms)

    # ------------------------------------------------------------------
    # Stage 4: Dedupe Cache
    # ------------------------------------------------------------------
    fresh_terms = dedupe_cache.run(active_terms, ignore_cache=ignore_cache)

    # ------------------------------------------------------------------
    # Stage 5: Regex Anchor Check
    # ------------------------------------------------------------------
    llm_candidates, regex_decided = regex_anchor_check.run(fresh_terms)
    below_regex_negates: list[dict] = []  # below-threshold terms are dropped entirely

    # ------------------------------------------------------------------
    # Stage 6: LLM Classification
    # ------------------------------------------------------------------
    all_anchors = regex_anchor_check.get_all_own_anchors()
    llm_classified, llm_calls, estimated_llm_cost = llm_classify_batch.run(
        llm_candidates, all_anchors
    )

    # ------------------------------------------------------------------
    # Stage 7: Confidence Gate (score threshold)
    # ------------------------------------------------------------------
    all_scored = confidence_gate.run(regex_decided, llm_classified)

    # ------------------------------------------------------------------
    # Stage 8: Scope Router
    # ------------------------------------------------------------------
    ag_level, campaign_level, keep_terms = scope_router.run(all_scored)

    # ------------------------------------------------------------------
    # Stage 9: Dry-Run Report (always)
    # ------------------------------------------------------------------
    report_terms = ag_level + campaign_level + keep_terms + protected_terms
    report_path = dry_run_report.run(report_terms)
    print(f"\nReport: {report_path}")

    if config.DRY_RUN:
        print("\nDRY RUN — no mutations sent.")
        if write_cache:
            update_cache.run(all_scored + protected_terms)
        else:
            print("DRY RUN — local cache not updated. Pass --write-cache to persist classifications.")
        _print_summary(
            terms, active_terms, protected_terms, fresh_terms,
            ag_level, keep_terms, llm_calls, estimated_llm_cost,
            ag_uploaded=0, run_start=run_start,
        )
        return

    # ------------------------------------------------------------------
    # Stage 10: Upload Negatives
    # ------------------------------------------------------------------
    ag_uploaded, camp_uploaded, deferred_terms = upload_negatives.run(
        customer_id, ag_level, campaign_level
    )

    # ------------------------------------------------------------------
    # Stage 11: Update Cache
    # ------------------------------------------------------------------
    # Exclude deferred terms so they resurface on the next run.
    deferred_keys = {(t.get("region_key"), t["term"].lower().strip()) for t in deferred_terms}
    all_classified = [
        t for t in all_scored + protected_terms
        if (t.get("region_key"), t["term"].lower().strip()) not in deferred_keys
    ]
    update_cache.run(all_classified)

    _print_summary(
        terms, active_terms, protected_terms, fresh_terms,
        ag_level, keep_terms, llm_calls, estimated_llm_cost,
        ag_uploaded=ag_uploaded, run_start=run_start,
    )


def _print_summary(
    terms, active_terms, protected_terms, fresh_terms,
    ag_level, keep_terms, llm_calls, estimated_llm_cost,
    ag_uploaded, run_start,
) -> None:
    elapsed = time.time() - run_start
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"  Total terms pulled         : {len(terms)}")
    print(f"  Protected (CV >= threshold): {len(protected_terms)}")
    print(f"  Active (cost >= threshold) : {len(active_terms)}")
    print(f"  Fresh (after dedup)        : {len(fresh_terms)}")
    print(f"  Negated AG-level           : {len(ag_level)}  (uploaded: {ag_uploaded})")
    print(f"  Kept (no action)           : {len(keep_terms)}")
    print(f"  LLM API calls              : {llm_calls}")
    print(f"  Estimated LLM cost         : ${estimated_llm_cost:.4f}")
    print(f"  Total elapsed              : {elapsed:.1f}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

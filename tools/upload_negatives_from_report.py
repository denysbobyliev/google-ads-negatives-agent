from __future__ import annotations
"""Upload exact-match negatives from a reviewed dry-run report."""

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import pull_scope
import upload_negatives


DEFAULT_EXCLUDES = {"bumble italy", "bumble italia"}


def _excluded(term: str, excludes: set[str]) -> bool:
    normalized = term.lower().strip()
    return normalized in excludes or normalized.startswith("viking dating")


def _load_rows(path: str, excludes: set[str]) -> tuple[list[dict], list[dict], list[dict]]:
    ag_rows = []
    campaign_rows = []
    skipped = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("action") != "NEGATE":
                continue
            if _excluded(row.get("term", ""), excludes):
                skipped.append(row)
                continue
            if row.get("target_scope") == "ad_group":
                ag_rows.append(row)
            elif row.get("target_scope") == "campaign":
                campaign_rows.append(row)
    return ag_rows, campaign_rows, skipped


def _scope_maps(scope: list[dict]) -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
    ad_groups = {}
    campaigns = {}
    for row in scope:
        ad_groups[(row["campaign_name"], row["ad_group_name"])] = row
        campaigns[row["campaign_name"]] = {
            "campaign_id": row["campaign_id"],
            "campaign_resource": row["campaign_resource"],
        }
    return ad_groups, campaigns


def _prepare_ag_rows(rows: list[dict], ad_groups: dict[tuple[str, str], dict]) -> list[dict]:
    prepared = []
    missing = set()
    for row in rows:
        meta = ad_groups.get((row["campaign_name"], row["ad_group_name"]))
        if not meta:
            missing.add((row["campaign_name"], row["ad_group_name"]))
            continue
        prepared.append({**row, **meta})
    if missing:
        raise RuntimeError(f"Could not resolve ad groups from current scope: {sorted(missing)}")
    return prepared


def _prepare_campaign_rows(rows: list[dict], campaigns: dict[str, dict]) -> list[dict]:
    prepared = []
    missing = set()
    for row in rows:
        meta = campaigns.get(row["campaign_name"])
        if not meta:
            missing.add(row["campaign_name"])
            continue
        prepared.append({**row, **meta})
    if missing:
        raise RuntimeError(f"Could not resolve campaigns from current scope: {sorted(missing)}")
    return prepared


def _build_campaign_operations_no_cap(
    client,
    campaign_terms: list[dict],
    existing_campaign_negatives: dict[str, set[str]],
) -> dict[str, list]:
    by_campaign: dict[str, list[dict]] = defaultdict(list)
    for term in campaign_terms:
        by_campaign[term["campaign_resource"]].append(term)

    ops_by_campaign: dict[str, list] = {}
    for campaign_resource, terms in by_campaign.items():
        campaign_id = campaign_resource.split("/")[-1]
        existing = existing_campaign_negatives.get(campaign_id, set())
        proposed: set[str] = set()
        operations = []
        already_exists = 0
        for term in terms:
            text = term["term"].lower().strip()
            dedup_key = f"EXACT::{text}"
            if dedup_key in proposed:
                continue
            proposed.add(dedup_key)
            if dedup_key in existing:
                already_exists += 1
                continue
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = campaign_resource
            criterion.negative = True
            criterion.keyword.text = term["term"]
            criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
            operations.append(operation)
        print(
            f"  [dedup] campaign {campaign_id}: {len(terms)} proposed, "
            f"{len(existing)} existing negatives in account, "
            f"{already_exists} skipped (already exact-match negative), "
            f"{len(operations)} to upload"
        )
        if operations:
            ops_by_campaign[campaign_resource] = operations
    return ops_by_campaign


def _summarize(ag_rows: list[dict], campaign_rows: list[dict], skipped: list[dict]) -> None:
    print(f"AG-level negatives in report after exclusions: {len(ag_rows)}")
    print(f"Campaign-level negatives in report after exclusions: {len(campaign_rows)}")
    print(f"Skipped/reverted terms: {len(skipped)}")
    for row in skipped:
        print(f"  skip: {row['term']} | {row['campaign_name']} / {row['ad_group_name']} | cost={row.get('cost')}")
    print("AG negatives by campaign:")
    for campaign, count in sorted(Counter(row["campaign_name"] for row in ag_rows).items()):
        print(f"  {campaign}: {count}")
    print("Campaign negatives by campaign:")
    for campaign, count in sorted(Counter(row["campaign_name"] for row in campaign_rows).items()):
        print(f"  {campaign}: {count}")


def run(args: argparse.Namespace) -> int:
    config.apply_account_profile(args.account_profile)
    customer_id = (args.customer_id or config.CUSTOMER_ID).replace("-", "")
    excludes = DEFAULT_EXCLUDES | {term.lower().strip() for term in args.exclude_term}

    ag_rows, campaign_rows, skipped = _load_rows(args.report, excludes)
    _summarize(ag_rows, campaign_rows, skipped)
    if not ag_rows and not campaign_rows:
        print("Nothing to upload.")
        return 0

    scope, _, _ = pull_scope.run(customer_id)
    ad_groups, campaigns = _scope_maps(scope)
    prepared_ag = _prepare_ag_rows(ag_rows, ad_groups)
    prepared_campaign = _prepare_campaign_rows(campaign_rows, campaigns)

    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")
    existing_ag = upload_negatives._fetch_ag_negatives(
        ga_service,
        customer_id,
        sorted({row["ad_group_id"] for row in prepared_ag}),
    )
    existing_campaign = upload_negatives._fetch_campaign_negatives(
        ga_service,
        customer_id,
        sorted({row["campaign_id"] for row in prepared_campaign}),
    )

    ops_by_ag, deferred = upload_negatives._build_ag_operations(client, prepared_ag, existing_ag)
    ops_by_campaign = _build_campaign_operations_no_cap(client, prepared_campaign, existing_campaign)

    ag_ops = sum(len(ops) for ops in ops_by_ag.values())
    campaign_ops = sum(len(ops) for ops in ops_by_campaign.values())
    print(f"New exact-match AG negatives to upload after account dedupe: {ag_ops}")
    print(f"New exact-match campaign negatives to upload after account dedupe: {campaign_ops}")
    if deferred:
        print(f"Deferred by AG cap: {len(deferred)}")

    if args.dry_run:
        print("DRY RUN - no changes made. Pass --no-dry-run to apply.")
        return 0

    ag_uploaded = upload_negatives._mutate_ag(client, customer_id, ops_by_ag)
    campaign_uploaded = upload_negatives._mutate_campaign(client, customer_id, ops_by_campaign)
    print(f"Uploaded {ag_uploaded} AG-level and {campaign_uploaded} campaign-level exact-match negatives.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--account-profile", default=config.DEFAULT_ACCOUNT_PROFILE)
    parser.add_argument("--customer-id", default=None)
    parser.add_argument("--exclude-term", action="append", default=[])
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

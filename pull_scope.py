from __future__ import annotations
"""
Stage 1: Pull Scope
Find all ad groups carrying the master label '<MASTER_AD_GROUP_LABEL>',
then resolve each to a region_key via its companion '<REGION_LABEL_PREFIX>*' label.
"""

import os
import sys
import time
import yaml
from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(__file__))
import config

MASTER_LABEL = "<MASTER_AD_GROUP_LABEL>"
REGION_LABEL_PREFIX = "<REGION_LABEL_PREFIX>"


def _load_region_keys() -> set[str]:
    with open(config.REGIONS_YAML) as f:
        return set(yaml.safe_load(f)["regions"].keys())


def run(customer_id: str, region_filter: str | None = None) -> list[dict]:
    t0 = time.time()
    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")
    known_regions = _load_region_keys()

    # ── Step 1: all ad groups with master label ──────────────────────────
    q1 = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.resource_name,
            campaign.id,
            campaign.name,
            campaign.resource_name
        FROM ad_group_label
        WHERE label.name = '{MASTER_LABEL}'
            AND ad_group.status != 'REMOVED'
            AND campaign.status != 'REMOVED'
    """
    ag_meta: dict[str, dict] = {}
    for row in ga_service.search(customer_id=customer_id, query=q1):
        ag_id = str(row.ad_group.id)
        ag_meta[ag_id] = {
            "ad_group_id": ag_id,
            "ad_group_name": row.ad_group.name,
            "ad_group_resource": row.ad_group.resource_name,
            "campaign_id": str(row.campaign.id),
            "campaign_name": row.campaign.name,
            "campaign_resource": row.campaign.resource_name,
        }

    if not ag_meta:
        print(f"Stage 1 — pull_scope: no ad groups found with label '{MASTER_LABEL}'")
        return []

    # ── Step 2: region labels for those ad groups ────────────────────────
    ids_csv = ", ".join(ag_meta.keys())
    q2 = f"""
        SELECT ad_group.id, label.name
        FROM ad_group_label
        WHERE ad_group.id IN ({ids_csv})
            AND ad_group.status != 'REMOVED'
    """
    ag_region: dict[str, str] = {}
    for row in ga_service.search(customer_id=customer_id, query=q2):
        ag_id = str(row.ad_group.id)
        label = row.label.name
        if label.startswith(REGION_LABEL_PREFIX):
            rk = label[len(REGION_LABEL_PREFIX):]
            if rk in known_regions:
                ag_region[ag_id] = rk

    # ── Step 3: join and (optionally) filter by region ───────────────────
    scope = []
    unmapped = []
    for ag_id, meta in ag_meta.items():
        rk = ag_region.get(ag_id)
        if rk is None:
            unmapped.append(meta["ad_group_name"])
            continue
        if region_filter and rk != region_filter:
            continue
        scope.append({**meta, "region_key": rk})

    if unmapped:
        print(f"  WARNING: {len(unmapped)} ad group(s) have no <REGION_LABEL_PREFIX>* label: {unmapped}")

    elapsed = time.time() - t0
    print(f"Stage 1 — pull_scope: {len(scope)} ad groups in {elapsed:.1f}s")
    return scope


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--customer-id", default=config.CUSTOMER_ID)
    p.add_argument("--region", default=None)
    args = p.parse_args()
    result = run(args.customer_id, region_filter=args.region)
    print(f"\nTotal ad groups in scope: {len(result)}")
    for ag in result:
        print(f"  [{ag['region_key']}] {ag['ad_group_name']} ({ag['campaign_name']})")

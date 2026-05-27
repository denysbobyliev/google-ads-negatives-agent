from __future__ import annotations
"""
Stage 1: Pull Scope
Find all ad groups carrying the configured master label and build the live
ad-group inventory injected into the classifier prompt.
"""

import os
import sys
import time
from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(__file__))
import config


def build_inventory(scope: list[dict]) -> tuple[str, dict[str, str]]:
    """Return (prompt_inventory_text, {ad_group_name: campaign_name})."""
    inventory_map = {
        ag["ad_group_name"]: ag["campaign_name"]
        for ag in sorted(scope, key=lambda x: (x["campaign_name"], x["ad_group_name"]))
    }
    inventory_text = "\n".join(
        f"{ad_group}\t{campaign}"
        for ad_group, campaign in inventory_map.items()
    )
    return inventory_text, inventory_map


def run(
    customer_id: str,
    region_filter: str | None = None,
) -> tuple[list[dict], str, dict[str, str]]:
    t0 = time.time()
    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")

    q1 = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.resource_name,
            campaign.id,
            campaign.name,
            campaign.resource_name
        FROM ad_group_label
        WHERE label.name = '{config.MASTER_LABEL}'
            AND ad_group.status = 'ENABLED'
            AND campaign.status = 'ENABLED'
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
        print(f"Stage 1 — pull_scope: no ad groups found with label '{config.MASTER_LABEL}'")
        return [], "", {}

    scope = list(ag_meta.values())
    if region_filter:
        needle = region_filter.lower().replace("_", " ")
        scope = [
            ag for ag in scope
            if ag["ad_group_name"].lower() == needle
            or ag["ad_group_name"].lower().replace(" ", "_") == region_filter.lower()
        ]

    inventory_text, inventory_map = build_inventory(scope)

    elapsed = time.time() - t0
    print(
        f"Stage 1 — pull_scope: {len(scope)} ad groups, "
        f"{len(inventory_map)} inventory entries in {elapsed:.1f}s"
    )
    return scope, inventory_text, inventory_map


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--customer-id", default=config.CUSTOMER_ID)
    p.add_argument("--region", default=None)
    args = p.parse_args()
    result, inventory_text, _ = run(args.customer_id, region_filter=args.region)
    print(f"\nTotal ad groups in scope: {len(result)}")
    for ag in result:
        print(f"  {ag['ad_group_name']} ({ag['campaign_name']})")
    print("\nInventory:\n" + inventory_text)

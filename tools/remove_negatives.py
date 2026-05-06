from __future__ import annotations
"""
One-off utility: remove specific negative keywords from ad groups.

Usage (dry-run by default):
  python remove_negatives.py --customer-id <GOOGLE_ADS_CUSTOMER_ID> --dry-run

  python remove_negatives.py --customer-id <GOOGLE_ADS_CUSTOMER_ID> --no-dry-run

Finds every ad group in scope (same label filter as the main pipeline) and
removes EXACT-match negatives whose text matches any entry in TERMS_TO_REMOVE.
"""

import argparse
import os
import sys
from collections import defaultdict

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

# Terms to remove — lowercase, exact text as they appear in Google Ads
TERMS_TO_REMOVE: set[str] = {
    "buziak uk",
    "randki uk",
    "asians near me",
}


def _fetch_scope(ga_service, customer_id: str) -> list[dict]:
    """Return ad groups labelled '<MASTER_AD_GROUP_LABEL>', same as pull_scope."""
    import yaml
    with open(config.REGIONS_YAML) as f:
        known_regions = set(yaml.safe_load(f)["regions"].keys())

    q1 = """
        SELECT ad_group.id, ad_group.name, ad_group.resource_name,
               campaign.name
        FROM ad_group_label
        WHERE label.name = '<MASTER_AD_GROUP_LABEL>'
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
            "campaign_name": row.campaign.name,
        }

    if not ag_meta:
        return []

    ids_csv = ", ".join(ag_meta.keys())
    q2 = f"""
        SELECT ad_group.id, label.name
        FROM ad_group_label
        WHERE ad_group.id IN ({ids_csv})
          AND ad_group.status != 'REMOVED'
    """
    for row in ga_service.search(customer_id=customer_id, query=q2):
        ag_id = str(row.ad_group.id)
        label = row.label.name
        if label.startswith("<REGION_LABEL_PREFIX>"):
            rk = label[len("<REGION_LABEL_PREFIX>"):]
            if rk in known_regions:
                ag_meta[ag_id]["region_key"] = rk

    return list(ag_meta.values())


def _find_matching_criteria(
    ga_service, customer_id: str, ag_ids: list[str]
) -> list[tuple[str, str, str]]:
    """
    Returns list of (criterion_resource_name, term_text, ad_group_name)
    for EXACT-match negatives whose text is in TERMS_TO_REMOVE.
    """
    ids_csv = ", ".join(ag_ids)
    query = f"""
        SELECT
            ad_group.name,
            ad_group_criterion.resource_name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type
        FROM ad_group_criterion
        WHERE ad_group.id IN ({ids_csv})
          AND ad_group_criterion.negative = TRUE
          AND ad_group_criterion.type = KEYWORD
          AND ad_group_criterion.status != 'REMOVED'
    """
    found = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        text = row.ad_group_criterion.keyword.text.lower().strip()
        match_type = row.ad_group_criterion.keyword.match_type.name
        if match_type == "EXACT" and text in TERMS_TO_REMOVE:
            found.append((
                row.ad_group_criterion.resource_name,
                text,
                row.ad_group.name,
            ))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-id", required=True)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")

    print(f"\nScanning ad groups in account {args.customer_id}…")
    scope = _fetch_scope(ga_service, args.customer_id)
    if not scope:
        print("No ad groups in scope.")
        return
    print(f"  {len(scope)} ad groups found.\n")

    ag_ids = [s["ad_group_id"] for s in scope]
    matches = _find_matching_criteria(ga_service, args.customer_id, ag_ids)

    if not matches:
        print("None of the target terms are currently negative keywords. Nothing to do.")
        return

    print(f"Found {len(matches)} negative(s) to remove:")
    for resource, text, ag_name in matches:
        print(f"  [{ag_name}] '{text}'  →  {resource}")

    if args.dry_run:
        print("\nDRY RUN — no changes made. Pass --no-dry-run to apply.")
        return

    # Build REMOVE operations
    service = client.get_service("AdGroupCriterionService")
    operations = []
    for resource, text, ag_name in matches:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = resource
        operations.append(op)

    request = client.get_type("MutateAdGroupCriteriaRequest")
    request.customer_id = args.customer_id
    request.operations.extend(operations)
    request.partial_failure = True

    response = service.mutate_ad_group_criteria(request=request)
    if response.partial_failure_error.code != 0:
        print(f"Partial failure: {response.partial_failure_error}")
    else:
        print(f"\nSuccessfully removed {len(operations)} negative(s).")


if __name__ == "__main__":
    main()

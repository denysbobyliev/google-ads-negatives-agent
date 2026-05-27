from __future__ import annotations
"""Remove exact-match negative keywords from ad groups and campaigns."""

import argparse
import os
import sys

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_ag_negatives(ga_service, customer_id: str, terms: set[str]) -> list[dict]:
    terms_csv = ", ".join(f"'{_quote(term)}'" for term in sorted(terms))
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_criterion.resource_name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type
        FROM ad_group_criterion
        WHERE ad_group_criterion.negative = TRUE
          AND ad_group_criterion.type = KEYWORD
          AND ad_group_criterion.status != 'REMOVED'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
          AND ad_group_criterion.keyword.match_type = EXACT
          AND ad_group_criterion.keyword.text IN ({terms_csv})
    """
    found = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        found.append(
            {
                "level": "ad_group",
                "resource": row.ad_group_criterion.resource_name,
                "campaign": row.campaign.name,
                "ad_group": row.ad_group.name,
                "term": row.ad_group_criterion.keyword.text,
            }
        )
    return found


def _find_campaign_negatives(ga_service, customer_id: str, terms: set[str]) -> list[dict]:
    terms_csv = ", ".join(f"'{_quote(term)}'" for term in sorted(terms))
    query = f"""
        SELECT
            campaign.name,
            campaign_criterion.resource_name,
            campaign_criterion.keyword.text,
            campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign_criterion.negative = TRUE
          AND campaign_criterion.type = KEYWORD
          AND campaign_criterion.status != 'REMOVED'
          AND campaign.status != 'REMOVED'
          AND campaign_criterion.keyword.match_type = EXACT
          AND campaign_criterion.keyword.text IN ({terms_csv})
    """
    found = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        found.append(
            {
                "level": "campaign",
                "resource": row.campaign_criterion.resource_name,
                "campaign": row.campaign.name,
                "ad_group": "",
                "term": row.campaign_criterion.keyword.text,
            }
        )
    return found


def _mutate(client, customer_id: str, matches: list[dict]) -> tuple[int, int]:
    ag_ops = []
    campaign_ops = []
    for match in matches:
        if match["level"] == "ad_group":
            op = client.get_type("AdGroupCriterionOperation")
            op.remove = match["resource"]
            ag_ops.append(op)
        else:
            op = client.get_type("CampaignCriterionOperation")
            op.remove = match["resource"]
            campaign_ops.append(op)

    ag_removed = 0
    campaign_removed = 0
    if ag_ops:
        service = client.get_service("AdGroupCriterionService")
        request = client.get_type("MutateAdGroupCriteriaRequest")
        request.customer_id = customer_id
        request.operations.extend(ag_ops)
        request.partial_failure = True
        response = service.mutate_ad_group_criteria(request=request)
        if response.partial_failure_error.code != 0:
            print(f"AG partial failure: {response.partial_failure_error}")
        ag_removed = len(response.results)

    if campaign_ops:
        service = client.get_service("CampaignCriterionService")
        request = client.get_type("MutateCampaignCriteriaRequest")
        request.customer_id = customer_id
        request.operations.extend(campaign_ops)
        request.partial_failure = True
        response = service.mutate_campaign_criteria(request=request)
        if response.partial_failure_error.code != 0:
            print(f"Campaign partial failure: {response.partial_failure_error}")
        campaign_removed = len(response.results)

    return ag_removed, campaign_removed


def run(args: argparse.Namespace) -> int:
    config.apply_account_profile(args.account_profile)
    customer_id = (args.customer_id or config.CUSTOMER_ID).replace("-", "")
    terms = {term.lower().strip() for term in args.term if term.strip()}
    if not terms:
        print("No terms provided.")
        return 0

    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")
    matches = _find_ag_negatives(ga_service, customer_id, terms)
    matches.extend(_find_campaign_negatives(ga_service, customer_id, terms))

    if not matches:
        print("No exact-match negatives found for requested terms.")
        return 0

    print(f"Found {len(matches)} exact-match negative(s) to remove:")
    for match in matches:
        where = match["campaign"]
        if match["ad_group"]:
            where += f" / {match['ad_group']}"
        print(f"  {match['level']}: {match['term']} | {where}")

    if args.dry_run:
        print("DRY RUN - no changes made. Pass --no-dry-run to apply.")
        return 0

    ag_removed, campaign_removed = _mutate(client, customer_id, matches)
    print(f"Removed {ag_removed} ad-group and {campaign_removed} campaign exact-match negatives.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-profile", default=config.DEFAULT_ACCOUNT_PROFILE)
    parser.add_argument("--customer-id", default=None)
    parser.add_argument("--term", action="append", required=True)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

from __future__ import annotations
"""
Stage 10: Upload Negatives
Uploads new negative keywords to Google Ads.
- Pulls existing negatives first; skips duplicates.
- Hard caps: max 50 new AG-level per ad group, max 50 campaign-level per campaign.
  Fails loud (raises) if cap would be exceeded — does NOT silently truncate.
- Uses proto-plus style on AdGroupCriterionService / CampaignCriterionService.
- partial_failure=True on all mutate calls; per-item errors logged without aborting.
- NO SharedSetService, NO SharedCriterionService.
"""

import os
import sys
import time
from collections import defaultdict

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(__file__))
import config
from llm_logger import log_upload_error


# ---------------------------------------------------------------------------
# Fetch existing negatives
# ---------------------------------------------------------------------------

def _fetch_ag_negatives(
    ga_service, customer_id: str, ad_group_ids: list[str]
) -> dict[str, set[str]]:
    """Returns {ad_group_id: set of lowercase exact-match negative texts}."""
    if not ad_group_ids:
        return {}
    ids_csv = ", ".join(ad_group_ids)
    query = f"""
        SELECT
            ad_group.id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type
        FROM ad_group_criterion
        WHERE ad_group.id IN ({ids_csv})
            AND ad_group_criterion.negative = TRUE
            AND ad_group_criterion.type = KEYWORD
            AND ad_group_criterion.status != 'REMOVED'
    """
    result: dict[str, set[str]] = defaultdict(set)
    for row in ga_service.search(customer_id=customer_id, query=query):
        ag_id = str(row.ad_group.id)
        text = row.ad_group_criterion.keyword.text.lower().strip()
        match_type = row.ad_group_criterion.keyword.match_type.name
        result[ag_id].add(f"{match_type}::{text}")
    return result


def _fetch_campaign_negatives(
    ga_service, customer_id: str, campaign_ids: list[str]
) -> dict[str, set[str]]:
    """Returns {campaign_id: set of lowercase exact-match negative texts}."""
    if not campaign_ids:
        return {}
    ids_csv = ", ".join(campaign_ids)
    query = f"""
        SELECT
            campaign.id,
            campaign_criterion.keyword.text,
            campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign.id IN ({ids_csv})
            AND campaign_criterion.negative = TRUE
            AND campaign_criterion.type = KEYWORD
            AND campaign_criterion.status != 'REMOVED'
    """
    result: dict[str, set[str]] = defaultdict(set)
    for row in ga_service.search(customer_id=customer_id, query=query):
        camp_id = str(row.campaign.id)
        text = row.campaign_criterion.keyword.text.lower().strip()
        match_type = row.campaign_criterion.keyword.match_type.name
        result[camp_id].add(f"{match_type}::{text}")
    return result


# ---------------------------------------------------------------------------
# Build operation lists
# ---------------------------------------------------------------------------

def _build_ag_operations(
    client,
    ag_terms: list[dict],
    existing_ag_negatives: dict[str, set[str]],
) -> tuple[dict[str, list], list[dict]]:
    """Returns ({ad_group_resource: [operations]}, deferred_terms).

    When LLM-sourced negatives for an ad group exceed MAX_AG_NEGATIVES_PER_RUN,
    the top terms by spend are taken and the rest are deferred (not uploaded and
    not cached, so they resurface on the next run).
    """
    by_ag: dict[str, list[dict]] = defaultdict(list)
    for t in ag_terms:
        by_ag[t["ad_group_resource"]].append(t)

    ops_by_ag: dict[str, list] = {}
    deferred: list[dict] = []

    for ag_resource, terms in by_ag.items():
        ag_id = ag_resource.split("/")[-1]
        existing = existing_ag_negatives.get(ag_id, set())

        llm_terms = [t for t in terms if t.get("source") != "regex"]
        regex_terms = [t for t in terms if t.get("source") == "regex"]

        if len(llm_terms) > config.MAX_AG_NEGATIVES_PER_RUN:
            llm_terms_sorted = sorted(llm_terms, key=lambda t: t.get("cost", 0.0), reverse=True)
            admitted = llm_terms_sorted[:config.MAX_AG_NEGATIVES_PER_RUN]
            deferred.extend(llm_terms_sorted[config.MAX_AG_NEGATIVES_PER_RUN:])
            print(
                f"  [cap] {ag_resource}: {len(llm_terms)} LLM negatives → "
                f"uploading top {len(admitted)} by spend, deferring {len(deferred)}"
            )
            terms_to_upload = regex_terms + admitted
        else:
            terms_to_upload = terms

        new_ops = []
        already_exists = 0
        for t in terms_to_upload:
            dedup_key = f"EXACT::{t['term'].lower().strip()}"
            if dedup_key in existing:
                already_exists += 1
                continue
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create
            criterion.ad_group = ag_resource
            criterion.negative = True
            criterion.keyword.text = t["term"]
            criterion.keyword.match_type = (
                client.enums.KeywordMatchTypeEnum.EXACT
            )
            new_ops.append(operation)

        print(
            f"  [dedup] AG {ag_id}: {len(terms_to_upload)} proposed, "
            f"{len(existing)} existing negatives in account, "
            f"{already_exists} skipped (already exact-match negative), "
            f"{len(new_ops)} to upload"
        )

        if new_ops:
            ops_by_ag[ag_resource] = new_ops

    return ops_by_ag, deferred


def _build_campaign_operations(
    client,
    campaign_terms: list[dict],
    existing_campaign_negatives: dict[str, set[str]],
) -> dict[str, list]:
    """Returns {campaign_resource: [operations]}. Raises if cap exceeded."""
    by_campaign: dict[str, list[dict]] = defaultdict(list)
    for t in campaign_terms:
        by_campaign[t["campaign_resource"]].append(t)

    ops_by_campaign: dict[str, list] = {}
    for camp_resource, terms in by_campaign.items():
        camp_id = camp_resource.split("/")[-1]
        existing = existing_campaign_negatives.get(camp_id, set())
        new_ops = []
        for t in terms:
            dedup_key = f"EXACT::{t['term'].lower().strip()}"
            if dedup_key in existing:
                continue
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = camp_resource
            criterion.negative = True
            criterion.keyword.text = t["term"]
            criterion.keyword.match_type = (
                client.enums.KeywordMatchTypeEnum.EXACT
            )
            new_ops.append(operation)

        if len(new_ops) > config.MAX_CAMPAIGN_NEGATIVES_PER_RUN:
            raise RuntimeError(
                f"Cap exceeded: {len(new_ops)} new campaign-level negatives for "
                f"{camp_resource} (max {config.MAX_CAMPAIGN_NEGATIVES_PER_RUN}). "
                f"Investigate before proceeding."
            )
        if new_ops:
            ops_by_campaign[camp_resource] = new_ops
    return ops_by_campaign


# ---------------------------------------------------------------------------
# Mutate calls
# ---------------------------------------------------------------------------

def _mutate_ag(client, customer_id: str, ops_by_ag: dict[str, list]) -> int:
    service = client.get_service("AdGroupCriterionService")
    uploaded = 0
    for ag_resource, operations in ops_by_ag.items():
        ag_id = ag_resource.split("/")[-1]
        try:
            request = client.get_type("MutateAdGroupCriteriaRequest")
            request.customer_id = customer_id
            request.operations.extend(operations)
            request.partial_failure = True
            response = service.mutate_ad_group_criteria(request=request)
            if response.partial_failure_error.code != 0:
                for error in response.partial_failure_error.details:
                    log_upload_error("ad_group", ag_id, "", str(error))
            uploaded += len(operations)
        except Exception as exc:
            log_upload_error("ad_group", ag_id, "", str(exc))
            print(f"  [error] AG {ag_id}: {exc}")
    return uploaded


def _mutate_campaign(client, customer_id: str, ops_by_campaign: dict[str, list]) -> int:
    service = client.get_service("CampaignCriterionService")
    uploaded = 0
    for camp_resource, operations in ops_by_campaign.items():
        camp_id = camp_resource.split("/")[-1]
        try:
            request = client.get_type("MutateCampaignCriteriaRequest")
            request.customer_id = customer_id
            request.operations.extend(operations)
            request.partial_failure = True
            response = service.mutate_campaign_criteria(request=request)
            if response.partial_failure_error.code != 0:
                for error in response.partial_failure_error.details:
                    log_upload_error("campaign", camp_id, "", str(error))
            uploaded += len(operations)
        except Exception as exc:
            log_upload_error("campaign", camp_id, "", str(exc))
            print(f"  [error] campaign {camp_id}: {exc}")
    return uploaded


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    customer_id: str,
    ag_level: list[dict],
    campaign_level: list[dict],
) -> tuple[int, int, list[dict]]:
    """Returns (ag_uploaded_count, campaign_uploaded_count, deferred_terms).

    deferred_terms are LLM-classified negatives that exceeded the per-ad-group
    cap and were not uploaded. Callers must exclude them from the cache so they
    resurface on the next run.
    """
    t0 = time.time()

    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")

    # Pull existing negatives for all affected entities
    ag_ids = list({t["ad_group_id"] for t in ag_level})
    camp_ids = list({t["campaign_id"] for t in campaign_level})

    existing_ag = _fetch_ag_negatives(ga_service, customer_id, ag_ids)
    existing_campaign = _fetch_campaign_negatives(ga_service, customer_id, camp_ids)

    ops_by_ag, deferred = _build_ag_operations(client, ag_level, existing_ag)
    ops_by_camp = _build_campaign_operations(client, campaign_level, existing_campaign)

    ag_uploaded = _mutate_ag(client, customer_id, ops_by_ag)
    camp_uploaded = _mutate_campaign(client, customer_id, ops_by_camp)

    elapsed = time.time() - t0
    deferred_note = f", {len(deferred)} deferred to next run" if deferred else ""
    print(
        f"Stage 10 — upload_negatives: {ag_uploaded} AG-level, "
        f"{camp_uploaded} campaign-level uploaded{deferred_note} (in {elapsed:.1f}s)"
    )
    return ag_uploaded, camp_uploaded, deferred

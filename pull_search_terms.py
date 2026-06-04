from __future__ import annotations
"""
Stage 2: Pull Search Terms
For each ad group in scope, pull search terms with click/cost/conversion metrics
over the configured date window.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(__file__))
import config


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _empty_metrics_record(row, ag_id: str, term: str) -> dict:
    return {
        "term": term,
        "ad_group_id": ag_id,
        "ad_group_name": row.ad_group.name,
        "ad_group_resource": row.ad_group.resource_name,
        "campaign_id": str(row.campaign.id),
        "campaign_name": row.campaign.name,
        "campaign_resource": row.campaign.resource_name,
        "clicks": 0,
        "cost": 0.0,
        "conversions": 0.0,
        "conversions_value": 0.0,
    }


def _query_chunk(customer_id: str, ag_ids: list[str], date_range: str) -> dict[tuple, dict]:
    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")
    ids_csv = ", ".join(ag_ids)
    query = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.status,
            ad_group.id,
            ad_group.name,
            ad_group.resource_name,
            campaign.id,
            campaign.name,
            campaign.resource_name,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM search_term_view
        WHERE ad_group.id IN ({ids_csv})
            AND ad_group.status = 'ENABLED'
            AND campaign.status = 'ENABLED'
            AND {date_range}
            AND search_term_view.status NOT IN ('ADDED', 'EXCLUDED', 'ADDED_EXCLUDED')
        ORDER BY metrics.cost_micros DESC
    """
    chunk_raw: dict[tuple, dict] = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        ag_id = str(row.ad_group.id)
        term = row.search_term_view.search_term.strip().lower()
        key = (ag_id, term)
        if key not in chunk_raw:
            chunk_raw[key] = _empty_metrics_record(row, ag_id, term)
        chunk_raw[key]["clicks"] += row.metrics.clicks
        chunk_raw[key]["cost"] += row.metrics.cost_micros / 1_000_000
        chunk_raw[key]["conversions"] += row.metrics.conversions
        chunk_raw[key]["conversions_value"] += row.metrics.conversions_value
    return chunk_raw


def _merge_raw(target: dict[tuple, dict], source: dict[tuple, dict]) -> None:
    for key, rec in source.items():
        if key not in target:
            target[key] = rec
            continue
        target[key]["clicks"] += rec["clicks"]
        target[key]["cost"] += rec["cost"]
        target[key]["conversions"] += rec["conversions"]
        target[key]["conversions_value"] += rec["conversions_value"]


def run(
    customer_id: str,
    scope: list[dict],
    days: int = config.DAYS,
) -> list[dict]:
    t0 = time.time()

    today = date.today()
    start = today - timedelta(days=days)
    date_range = f"segments.date BETWEEN '{start}' AND '{today}'"

    ag_ids = [ag["ad_group_id"] for ag in scope]
    chunk_size = 100
    chunks = _chunked(ag_ids, chunk_size)
    raw: dict[tuple, dict] = {}

    workers = min(max(1, config.SEARCH_TERM_PULL_WORKERS), len(chunks) or 1)
    if workers == 1 or len(chunks) <= 1:
        for chunk in chunks:
            _merge_raw(raw, _query_chunk(customer_id, chunk, date_range))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_query_chunk, customer_id, chunk, date_range)
                for chunk in chunks
            ]
            for future in as_completed(futures):
                _merge_raw(raw, future.result())

    terms = []
    for rec in raw.values():
        rec["cost"] = round(rec["cost"], 4)
        rec["conversions"] = round(rec["conversions"], 4)
        rec["conversions_value"] = round(rec["conversions_value"], 4)
        terms.append(rec)

    elapsed = time.time() - t0
    print(
        f"Stage 2 — pull_search_terms: {len(terms)} terms, "
        f"{len(chunks)} chunk(s), workers={workers} in {elapsed:.1f}s"
    )
    return terms

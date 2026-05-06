from __future__ import annotations
"""
Stage 2: Pull Search Terms
For each ad group in scope, pull search terms with click/cost/conversion metrics
over the configured date window.
"""

import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(__file__))
import config


def run(
    customer_id: str,
    scope: list[dict],
    days: int = config.DAYS,
) -> list[dict]:
    t0 = time.time()
    client = GoogleAdsClient.load_from_storage(config.GOOGLE_ADS_YAML)
    ga_service = client.get_service("GoogleAdsService")

    today = date.today()
    start = today - timedelta(days=days)
    date_range = f"segments.date BETWEEN '{start}' AND '{today}'"

    ag_ids = [ag["ad_group_id"] for ag in scope]
    ag_meta = {ag["ad_group_id"]: ag for ag in scope}

    # Chunk to avoid query size limits
    chunk_size = 100
    raw: dict[tuple, dict] = {}

    for i in range(0, len(ag_ids), chunk_size):
        chunk = ag_ids[i : i + chunk_size]
        ids_csv = ", ".join(chunk)
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
                AND {date_range}
                AND search_term_view.status NOT IN ('EXCLUDED', 'ADDED_EXCLUDED')
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            ag_id = str(row.ad_group.id)
            term = row.search_term_view.search_term.strip().lower()
            key = (ag_id, term)
            if key not in raw:
                raw[key] = {
                    "term": term,
                    "ad_group_id": ag_id,
                    "ad_group_name": row.ad_group.name,
                    "ad_group_resource": row.ad_group.resource_name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "campaign_resource": row.campaign.resource_name,
                    "region_key": ag_meta[ag_id]["region_key"],
                    "clicks": 0,
                    "cost": 0.0,
                    "conversions": 0.0,
                    "conversions_value": 0.0,
                }
            raw[key]["clicks"] += row.metrics.clicks
            raw[key]["cost"] += row.metrics.cost_micros / 1_000_000
            raw[key]["conversions"] += row.metrics.conversions
            raw[key]["conversions_value"] += row.metrics.conversions_value

    terms = []
    for rec in raw.values():
        rec["cost"] = round(rec["cost"], 4)
        rec["conversions"] = round(rec["conversions"], 4)
        rec["conversions_value"] = round(rec["conversions_value"], 4)
        terms.append(rec)

    elapsed = time.time() - t0
    print(f"Stage 2 — pull_search_terms: {len(terms)} terms in {elapsed:.1f}s")
    return terms

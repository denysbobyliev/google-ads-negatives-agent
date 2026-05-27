from __future__ import annotations
"""
Stage 7: Route classifier output to concrete actions per served ad group.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config


def campaign_of(ad_group: str, inventory: dict[str, str]) -> str | None:
    return inventory.get(ad_group)


def lang_keepset(lang: str, inventory: dict[str, str], cfg: dict | None = None) -> set[str]:
    cfg = cfg or config.load_account_config()
    language_map = cfg.get("language_map", {})
    generals = cfg.get("generals", {})

    countries = {country for country in language_map.get(lang, []) if country in inventory}
    campaigns = {inventory[country] for country in countries if country in inventory}
    campaign_generals = {
        general for campaign, general in generals.items()
        if campaign in campaigns and general in inventory
    }
    return countries | campaign_generals


def route_to_action(
    route: str | None,
    served_ag: str,
    inventory: dict[str, str],
    cfg: dict | None = None,
) -> str:
    """Pure route-string resolver. Returns KEEP, NEGATE, or NOOP."""
    cfg = cfg or config.load_account_config()
    served_campaign = campaign_of(served_ag, inventory)

    if route in (None, "", "REVIEW"):
        return "NOOP"
    if route == "NEGATE_ALL":
        return "NEGATE"
    if route == "CAMPAIGN_PROTECT:source":
        return "KEEP"
    if route.startswith("CAMPAIGN_PROTECT:"):
        target_campaign = route.split(":", 1)[1]
        return "KEEP" if served_campaign == target_campaign else "NEGATE"
    if route.startswith("LANG_KEEP:"):
        lang = route.split(":", 1)[1]
        return "KEEP" if served_ag in lang_keepset(lang, inventory, cfg) else "NEGATE"
    return "KEEP" if route == served_ag else "NEGATE"


def make_resolver(inventory: dict[str, str], cfg: dict | None = None):
    cfg = cfg or config.load_account_config()
    return lambda route, served_ag: route_to_action(route, served_ag, inventory, cfg)


def resolve(route: str, served_ag: str, inventory: dict[str, str], row: dict | None = None) -> str:
    """Return KEEP, NEGATE, or NOOP for this served ad-group instance."""
    if row and row.get("force_keep_in") == served_ag:
        return "KEEP"
    return route_to_action(route, served_ag, inventory)


def _mark_common(row: dict, action: str) -> None:
    row["action"] = action
    row["decision"] = "KEEP" if action in {"KEEP", "NOOP"} else "NEGATE"
    row["score"] = row.get("confidence")
    row["anchor_found"] = row.get("route")


def run(
    terms: list[dict],
    inventory: dict[str, str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (ad_group_negatives, campaign_negatives, keep_or_noop_terms).
    NEGATE_ALL is routed to campaign-level negatives for the served campaign.
    """
    t0 = time.time()

    ag_level = []
    campaign_level = []
    keep_terms = []

    for original in terms:
        row = dict(original)
        route = row.get("route", "REVIEW")
        served_ag = row.get("ad_group_name", "")
        action = resolve(route, served_ag, inventory, row)
        _mark_common(row, action)

        if action != "NEGATE":
            row["target_scope"] = "none"
            keep_terms.append(row)
            continue

        if route == "NEGATE_ALL":
            row["target_scope"] = "campaign"
            campaign_level.append(row)
        else:
            row["target_scope"] = "ad_group"
            ag_level.append(row)

    elapsed = time.time() - t0
    print(
        f"Stage 7 — scope_router: {len(ag_level)} AG negatives, "
        f"{len(campaign_level)} campaign negatives, "
        f"{len(keep_terms)} keep/noop (in {elapsed:.1f}s)"
    )
    return ag_level, campaign_level, keep_terms

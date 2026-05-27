from __future__ import annotations
"""Propose geo-dependent golden-set routes for a new account inventory."""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import classify_batch
import config
import confidence_gate
import guards
import pull_scope

GOLDEN_PATH = os.path.join(
    config.BASE_DIR,
    "verticals",
    "dating_geo",
    "eval",
    "golden_set.csv",
)


def _load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _inventory_from_rows(rows: list[dict]) -> tuple[str, dict[str, str]]:
    inventory: dict[str, str] = {}
    for row in rows:
        ag = row.get("served_ad_group") or row.get("ad_group_name")
        campaign = row.get("served_campaign") or row.get("campaign_name")
        if ag and campaign:
            inventory[ag] = campaign
    inventory_text = "\n".join(
        f"{ag}\t{campaign}"
        for ag, campaign in sorted(inventory.items(), key=lambda x: (x[1], x[0]))
    )
    return inventory_text, inventory


def account_independent(route: str) -> bool:
    return route in {"NEGATE_ALL", "REVIEW", "CAMPAIGN_PROTECT:source"}


def _load_inventory(args, old_rows: list[dict]) -> tuple[str, dict[str, str]]:
    if args.inventory_csv:
        return _inventory_from_rows(_load_csv(args.inventory_csv))
    if args.live_inventory:
        config.apply_account_profile(args.account_profile)
        customer_id = (args.customer_id or config.CUSTOMER_ID).replace("-", "")
        _, inventory_text, inventory = pull_scope.run(customer_id)
        return inventory_text, inventory
    return _inventory_from_rows(old_rows)


def _propose(
    rows: list[dict],
    inventory_text: str,
    inventory: dict[str, str],
) -> dict[str, dict]:
    predictions, _, _, _ = classify_batch.classify_terms(
        [row["term"].lower().strip() for row in rows],
        inventory_text,
    )
    haiku_rows = [
        {"term": term, **pred, "source": "haiku", "escalated": False}
        for term, pred in predictions.items()
    ]
    rows_by_term = {row["term"].lower().strip(): row for row in rows}
    guard_rows = []
    for row in haiku_rows:
        source = rows_by_term.get(row["term"], {})
        guard_rows.append({
            **row,
            "ad_group_name": source.get("served_ad_group", ""),
            "campaign_name": source.get("served_campaign", ""),
        })
    guarded = guards.run(guard_rows, inventory)
    gated, _, _, _ = confidence_gate.run(guarded, inventory_text, inventory)
    return {row["term"]: row for row in gated}


def run(args) -> int:
    old_rows = _load_csv(args.old)
    inventory_text, inventory = _load_inventory(args, old_rows)
    geo_rows = [row for row in old_rows if not account_independent(row["final_route"])]
    proposals = _propose(geo_rows, inventory_text, inventory)

    fieldnames = list(old_rows[0].keys()) if old_rows else []
    if "needs_review" not in fieldnames:
        fieldnames.append("needs_review")

    carried = 0
    changed = 0
    out_rows = []
    for row in old_rows:
        out = dict(row)
        route = row["final_route"]
        if account_independent(route):
            out["needs_review"] = ""
            carried += 1
        else:
            proposal = proposals.get(row["term"].lower().strip(), {"route": route})
            new_route = proposal.get("route", route)
            if new_route == route:
                out["needs_review"] = ""
                carried += 1
            else:
                out["final_route"] = new_route
                out["needs_review"] = f"CHANGED from {route} -> confirm"
                changed += 1
        out_rows.append(out)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"carried over: {carried} | flagged CHANGED for review: {changed}")
    print(
        "Next: append ~50-80 of this account's highest-cost search terms for "
        "its own brands/languages, then run eval_golden.py."
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relabel golden set for a new inventory")
    parser.add_argument("--old", default=GOLDEN_PATH)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inventory-csv", default=None)
    parser.add_argument("--live-inventory", action="store_true", default=False)
    parser.add_argument("--account-profile", default=config.DEFAULT_ACCOUNT_PROFILE)
    parser.add_argument("--customer-id", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

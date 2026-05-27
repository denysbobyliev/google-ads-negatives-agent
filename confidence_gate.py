from __future__ import annotations
"""
Stage 6: sharp own-anchor confidence gate.

Haiku keeps can apply at high confidence. Haiku negates only apply directly when
the served ad group is not named by the term. Own-anchor negates, guard-flagged
rows, brand-compound rows, REVIEW, and low-confidence rows go to Sonnet.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import config
import escalate
import scope_router
from verticals.dating_geo.geo_anchor_map import build_anchor_index
from verticals.dating_geo.geo_gate import route_decision


def _g(row: dict, *names: str, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def gate(records, idx, resolve_action, escalate_fn, log=None):
    """Package-compatible gate used by eval harnesses.

    `escalate_fn` receives unique terms and returns `{term: sonnet_record}`.
    """
    apply_rows = []
    queue = []

    for row in records:
        served_ag = _g(row, "served_ad_group", "ad_group_name")
        if row.get("force_keep_in") == served_ag:
            row["action"] = "KEEP"
            row["gate"] = "apply"
            apply_rows.append(row)
            continue

        row["action"] = resolve_action(row.get("route"), served_ag)
        flag = str(row.get("flag") or "")
        guard_flagged = any(marker in flag for marker in ("GUARD2", "GUARD3", "GUARD4"))
        protected_brand = row.get("level") == "brand_compound"
        decision = route_decision(
            row,
            idx,
            served_ag,
            guard_flagged=guard_flagged,
            protected_brand=protected_brand,
        )
        row["gate"] = "escalate_guard" if decision == "escalate" and guard_flagged else decision
        if decision == "apply":
            apply_rows.append(row)
        else:
            queue.append(row)
            if log is not None:
                log.append(
                    (
                        row.get("term"),
                        served_ag,
                        row.get("route"),
                        row.get("action"),
                        "guard"
                        if guard_flagged
                        else "brand"
                        if protected_brand
                        else "own_anchor_negate"
                        if row.get("action") == "NEGATE"
                        else "low_conf",
                    )
                )

    sonnet_by_term = escalate_fn(sorted({row["term"] for row in queue})) if queue else {}
    for row in queue:
        sonnet_row = sonnet_by_term.get(row["term"])
        if sonnet_row is not None:
            row.update(sonnet_row)
            row["source"] = "sonnet"
            row["escalated"] = True
            row["action"] = resolve_action(row.get("route"), _g(row, "served_ad_group", "ad_group_name"))
        apply_rows.append(row)

    return apply_rows, queue


def run(
    haiku_results: list[dict],
    inventory_text: str,
    inventory: dict[str, str],
) -> tuple[list[dict], int, float, dict[str, int]]:
    t0 = time.time()
    idx = build_anchor_index(inventory)
    resolve_action = scope_router.make_resolver(inventory, config.load_account_config())

    queue_terms: list[str] = []

    def collect_terms(terms: list[str]) -> dict[str, dict]:
        queue_terms[:] = terms
        return {}

    apply_probe, queue = gate(
        [dict(row) for row in haiku_results],
        idx,
        resolve_action,
        collect_terms,
    )

    queued_ids = {id(row) for row in queue}
    apply_rows = [row for row in apply_probe if id(row) not in queued_ids]
    sonnet_rows, sonnet_calls, sonnet_cost, sonnet_usage = escalate.run(queue, inventory_text)
    result = apply_rows + sonnet_rows

    elapsed = time.time() - t0
    print(
        f"Stage 6 — confidence_gate: {len(apply_rows)} Haiku apply, "
        f"{len(queue)} escalated to Sonnet (in {elapsed:.1f}s)"
    )
    return result, sonnet_calls, sonnet_cost, sonnet_usage

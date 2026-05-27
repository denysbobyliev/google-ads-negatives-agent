"""
eval_golden.py — the pre-launch trust check (build brief 4e), wired to the full new stack.

Runs the golden set through Haiku (classify) + guards + the sharp confidence gate + Sonnet
escalation + the scope_router resolver, and reports ACTION-accuracy (KEEP vs NEGATE at the
served ad group) per test_category, plus the FALSE-NEGATE list (oracle=KEEP, pred=NEGATE) —
the dangerous error, which must be ~0.

Modes
  --selftest (default): no API. Prediction = oracle PER INSTANCE (round-trips multi-instance
             and dual-anchor terms). Validates the resolver + metrics arithmetic end to end:
             expect 100% action-accuracy and 0 false-negates.
  --live   : imports classify_batch / escalate (Agents 1 & 2) and guards.run_guards and runs
             for real. GUARD2 force_keep_in is required for dual-anchor terms.

Single source of truth: account config from config.load_account_config(classifier.md), the
resolver from scope_router. No config is duplicated here.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from config import load_account_config
from scope_router import route_to_action, make_resolver
from verticals.dating_geo.geo_anchor_map import build_anchor_index, GENERAL_STEMS, SUBREGION_STEMS
from confidence_gate import gate

GOLD_DEFAULT = "verticals/dating_geo/eval/golden_set.csv"
CLASSIFIER_DEFAULT = "verticals/dating_geo/prompts/classifier.md"
CLEAR = {"country_clean", "general", "subregion", "brand_mainstream", "generic_negate"}


def load_golden(path):
    return list(csv.DictReader(open(path, newline="", encoding="utf-8")))


def build_inventory(rows):
    inv = {r["served_ad_group"]: r["served_campaign"] for r in rows}
    for g in GENERAL_STEMS:
        inv.setdefault(g, None)
    for s in SUBREGION_STEMS:
        inv.setdefault(s, None)
    return inv


def run_pipeline(rows, inventory, cfg, idx, classify_fn, escalate_fn, guards_fn):
    resolve_action = make_resolver(inventory, cfg)               # route -> action (no fkeep)
    # 1. classify unique terms (Haiku, one decision per term)
    terms = sorted({r["term"] for r in rows})
    haiku = classify_fn(terms, inventory)                        # {term: {route, confidence, level, lang}}
    # 2. expand to per-(term, served_ad_group) instances
    records = []
    for r in rows:
        h = haiku[r["term"]]
        records.append({"term": r["term"], "served_ad_group": r["served_ad_group"],
                        "route": h["route"], "confidence": h.get("confidence", 0.0),
                        "level": h.get("level"), "lang": h.get("lang"),
                        "reason": h.get("reason", ""), "flag": "", "source": "haiku",
                        "escalated": False})
    # 3. guards (GUARD4 brand, GUARD1 telemetry, GUARD2 dual-anchor, GUARD3 gender backstop)
    records = [guards_fn(rec, inventory, idx, resolve_action) for rec in records]
    # 4. sharp gate + Sonnet escalation (terminal)
    applied, escalated = gate(records, idx, resolve_action, escalate_fn)
    pred = {(rec["term"], rec["served_ad_group"]): rec for rec in applied}
    return pred, escalated


def report(rows, pred_action_of, inventory, cfg):
    per = defaultdict(lambda: {"n": 0, "act_ok": 0, "route_ok": 0})
    false_negates, overall_ok = [], 0
    for r in rows:
        cat, served = r["test_category"], r["served_ad_group"]
        oracle_route = r["final_route"]
        oa = route_to_action(oracle_route, served, inventory, cfg)
        pa, pred_route, src, conf = pred_action_of(r)
        ok = (oa == pa)
        per[cat]["n"] += 1
        per[cat]["act_ok"] += ok
        per[cat]["route_ok"] += (pred_route == oracle_route)
        overall_ok += ok
        if oa == "KEEP" and pa == "NEGATE":
            false_negates.append((r["term"], served, oracle_route, pred_route, cat, src, conf))

    print("=" * 74)
    print(f"{'test_category':32s} {'n':>4} {'action-acc':>11} {'route-exact':>12}")
    print("-" * 74)
    worst = []
    for cat in sorted(per):
        d = per[cat]
        acc = 100 * d["act_ok"] / d["n"]
        bar = 95 if cat in CLEAR else 85
        tag = "  OK" if acc >= bar else "  <-- BELOW BAR"
        if acc < bar:
            worst.append((cat, acc, bar))
        print(f"{cat:32s} {d['n']:>4} {acc:>10.1f}% {100*d['route_ok']/d['n']:>11.1f}%"
              f"  ({'clear>=95' if cat in CLEAR else 'ambig>=85'}){tag}")
    print("-" * 74)
    N = len(rows)
    print(f"{'OVERALL':32s} {N:>4} {100*overall_ok/N:>10.1f}%")
    print()
    print(f"FALSE-NEGATES (oracle=KEEP, pred=NEGATE) — MUST be ~0: {len(false_negates)}")
    for t, ag, orc, prd, cat, src, conf in false_negates:
        print(f"   - {t!r:40s} served={ag:14s} oracle={orc} pred={prd} [{cat}] src={src} conf={conf}")
    return len(false_negates), overall_ok / N, worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=GOLD_DEFAULT)
    ap.add_argument("--classifier", default=CLASSIFIER_DEFAULT)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="Offline resolver/metrics check (default).")
    args = ap.parse_args()

    rows = load_golden(args.gold)
    cfg = load_account_config(args.classifier)
    inventory = build_inventory(rows)
    idx = build_anchor_index(inventory)

    if args.live:
        from classify_batch import classify_batch as _cb
        from escalate import escalate as _esc
        try:
            from guards import run_guards as guards_fn
        except ImportError:
            guards_fn = lambda rec, inv, idx, ra: rec
            print("WARNING: guards.run_guards missing — dual_anchor_keep will false-negate.\n")
        inv_text = "\n".join(f"{ag}\t{camp}" for ag, camp in inventory.items() if camp)
        classify_fn = lambda terms, inv: {r["term"]: r for r in _cb(terms, inv_text)}
        escalate_fn = lambda terms: {r["term"]: r for r in _esc(terms, inv_text)}
        pred, escalated = run_pipeline(rows, inventory, cfg, idx, classify_fn, escalate_fn, guards_fn)

        def pred_action_of(r):
            rec = pred[(r["term"], r["served_ad_group"])]
            return rec.get("action"), rec.get("route"), rec.get("source"), rec.get("confidence")

        n_fn, acc, worst = report(rows, pred_action_of, inventory, cfg)
        print(f"\nmode: LIVE   escalated instances: {len(escalated)}")
        print("PASS" if (n_fn == 0 and not worst) else
              f"REVIEW: {n_fn} false-negates; below-bar: {[w[0] for w in worst]}")
    else:
        oracle_route = {(r["term"], r["served_ad_group"]): r["final_route"] for r in rows}

        def pred_action_of(r):
            rt = oracle_route[(r["term"], r["served_ad_group"])]
            return route_to_action(rt, r["served_ad_group"], inventory, cfg), rt, "oracle", 1.0

        n_fn, acc, worst = report(rows, pred_action_of, inventory, cfg)
        ok = (n_fn == 0 and abs(acc - 1.0) < 1e-9)
        print("\nmode: SELFTEST (resolver+metrics; pred==oracle per instance)")
        print("HARNESS OK" if ok else "HARNESS DEFECT — selftest must be 100% / 0 FN")


if __name__ == "__main__":
    main()

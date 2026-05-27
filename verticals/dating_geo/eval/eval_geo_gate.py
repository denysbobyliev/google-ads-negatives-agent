"""
eval_geo_gate.py — does the deterministic detector have the recall to support the redesign?

SAFETY metric (the one that matters): of golden rows whose correct outcome depends on a
partner-geo signal (route is an ad group or LANG_KEEP, OR a homonym), how many does the
detector flag geo_bearing? A MISS here = a term Haiku would be allowed to negate = the
exact China/Haiti false-negate class. Target: ~100% recall; every miss is a defect to fix.

COST metric: of rows that are genuinely no-geo (generic/mainstream/origin-only that should
be Haiku-negated cheaply), how many get wrongly flagged geo_bearing? These cost a Sonnet
call, not money. Lower is better but it is not a safety failure.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from verticals.dating_geo.geo_anchor_map import build_anchor_index, GENERAL_STEMS, SUBREGION_STEMS
from verticals.dating_geo.geo_gate import detect_geo

DEFAULT_GOLD = "verticals/dating_geo/eval/golden_set.csv"

parser = argparse.ArgumentParser()
parser.add_argument("--gold", default=DEFAULT_GOLD)
args = parser.parse_args()

rows = list(csv.DictReader(open(args.gold, newline="", encoding="utf-8")))

# inventory = the served ad groups in the golden set + the generals/subregions that exist
served = {r["served_ad_group"] for r in rows}
inventory = {ag: None for ag in served} | {g: None for g in GENERAL_STEMS} | {s: None for s in SUBREGION_STEMS}
idx = build_anchor_index(inventory)

GEO_DEST = served - {"Asia","Europe","Slavic","Latina","Eastern","Scandinavia","Mediterranean",
                     "Iberia","Benelux","Balkan","Baltic","Caribbean","Hispanic","Eastern Europe"}
GENERALS = {"Asia","Europe","Slavic","Latina"}
SUBREGIONS = {"Eastern","Scandinavia","Mediterranean","Iberia","Benelux","Balkan","Baltic",
              "Caribbean","Hispanic","Eastern Europe"}

def bucket(r):
    route = r["final_route"]
    if route.startswith("LANG_KEEP"): return "safety"           # must be geo-bearing
    if route in GEO_DEST or route in GENERALS or route in SUBREGIONS: return "safety"
    if route == "REVIEW" and r["test_category"] in ("homonym","language_review","review_unknown"):
        # homonyms must escalate; coined-brand REVIEW is a brand branch, not geo
        return "safety" if r["test_category"] == "homonym" else "brand_or_review"
    if route == "CAMPAIGN_PROTECT:source": return "brand_or_review"   # brand branch, not geo
    if route == "NEGATE_ALL":
        # split: genuinely no-geo (should be Haiku-negate) vs geo-token-but-negate (ok to escalate)
        return "clean_negate"
    return "other"

stats = defaultdict(lambda: [0,0])   # bucket -> [n, flagged_geo]
misses, overflags = [], []
clean_geo_token_negates = []         # NEGATE_ALL that legitimately carry a token (escalation ok)

for r in rows:
    v = detect_geo(r["term"], idx)
    b = bucket(r)
    stats[b][0]+= 1
    if v.geo_bearing: stats[b][1]+=1
    if b == "safety" and not v.geo_bearing:
        misses.append((r, v))
    if b == "clean_negate" and v.geo_bearing:
        # is this a defensible escalation (real token present, e.g. native american indian,
        # homonym->negate) or a true over-flag of pure generic/origin?
        cat = r["test_category"]
        if cat in ("generic_negate","brand_mainstream","brand_compound_nogeo","origin_only",
                   "no_geo_clean_reason","anchor_no_target","origin_demographic_negate"):
            overflags.append((r, v))
        else:
            clean_geo_token_negates.append((r, v))

print("="*78)
print("SAFETY RECALL — geo-bearing terms the detector MUST catch (else Haiku may negate them)")
print("="*78)
n, f = stats["safety"]
print(f"  safety rows: {n}   flagged geo-bearing: {f}   RECALL = {100*f/n:.1f}%")
brand_misses = [
    (r, v)
    for r, v in misses
    if r["final_route"] == "CAMPAIGN_PROTECT:source"
    or "brand" in r["test_category"]
    or "triage_miss" in (r.get("kind", "") + r.get("note", ""))
]
true_misses = [(r, v) for r, v in misses if (r, v) not in brand_misses]
print(f"  MISSES covered by brand/triage branch: {len(brand_misses)}")
for r, v in brand_misses:
    print(f"    - {r['term']!r:42s} [{r['test_category']}] served={r['served_ad_group']} -> {r['final_route']}")
print(f"  TRUE safety misses (dangerous): {len(true_misses)}")
for r, v in true_misses:
    print(f"    - {r['term']!r:42s} [{r['test_category']}] served={r['served_ad_group']} -> {r['final_route']}")

print()
print("="*78)
print("COST — no-geo rows wrongly flagged geo-bearing (unnecessary Sonnet calls, not money)")
print("="*78)
n, f = stats["clean_negate"]
print(f"  clean_negate rows: {n}   flagged geo-bearing: {f}")
print(f"  TRUE over-flags (pure generic/origin pushed to Sonnet): {len(overflags)}")
for r, v in overflags:
    print(f"    - {r['term']!r:42s} [{r['test_category']}]  hits={v.reason}")
print(f"  defensible escalations (NEGATE_ALL but a real token present -> Sonnet negates): {len(clean_geo_token_negates)}")
for r, v in clean_geo_token_negates:
    print(f"    - {r['term']!r:42s} [{r['test_category']}]  hits={v.reason}")

print()
print("="*78)
print("REAL RUN false-negates — would the gate now catch them?")
print("="*78)
run_fns = [
  ("best chinese dating app uk","China"), ("haitian dating app","Haiti"),
  ("site de rencontre femme asiatique","Asia"), ("asian swingers","Asia"),
  ("asian live cams","Asia"),
  # controls that SHOULD stay Haiku-negate-eligible (no geo):
  ("best uk dating app","-"), ("free cuckold dating sites","-"), ("tinder","-"),
  ("american women dating","-"), ("women from odessa us","-"),
]
for term, _ in run_fns:
    v = detect_geo(term, idx)
    verdict = "ESCALATE (Haiku cannot negate)" if v.geo_bearing else "Haiku-negate-eligible"
    print(f"  {term!r:40s} geo_bearing={v.geo_bearing!s:5s} -> {verdict:32s} [{v.reason}]")

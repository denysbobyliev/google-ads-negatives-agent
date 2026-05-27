"""
guards.py  (rebuilt — reconciled with the sharp gate)
=====================================================
Deterministic guards that run AFTER classify_batch and BEFORE confidence_gate. They no
longer carry the load they did in runs 1-4; the gate now owns the false-negate signature.
What changed and why (from the run report + the gate redesign):

  GUARD1  — DEMOTED to telemetry. Its job ("term names its served country -> force keep")
            is now the gate's `served_anchor_in_term`, generalized to country/general/
            sub-region and applied as escalate-not-force. Run 4 showed GUARD1 was overridable
            anyway (7 of 49 fires ended NEGATE after Sonnet) and misfired on homonyms
            (Panama City FL). So it no longer rewrites routes; it only annotates, so shadow
            logs still show "named its served group" without a second enforcement layer
            fighting the gate.

  GUARD2  — FIXED + NARROWED. Two bugs in run 4: (a) substring collision — 'eastern european
            women' served in the Asian 'Eastern' bucket was force-kept because bare 'eastern'
            matched the group name (it's Slavic, should cross-negate). Fixed centrally in
            geo_gate.served_anchor_in_term (eastern-european suppression). (b) scope — it
            force-kept on a SINGLE own-anchor, stealing terms the gate should escalate for
            Sonnet's nuance (asian swingers, bumble thailand). Now it fires ONLY on genuine
            DUAL-anchor: the served group's own target anchor AND a second distinct partner
            geo (the literal Phuket case — 'russian women in phuket' belongs in both Thailand
            and Russia). That is the one case a single per-term route cannot express, so it
            needs a deterministic keep; everything else single-anchor goes to the gate.

  GUARD3  — FIXED. Run 4 logged "GUARD3 ... -> NOOP" while the row stayed NEGATE_ALL/NEGATE.
            The "-> NOOP" branch was both a lie (flag != action) and wrong policy (NOOP keeps
            generic junk; there is no human queue). GUARD3 now acts ONLY when it can restore
            a real partner route: if a NEGATE_ALL is justified by invented gender/audience
            policy AND a partner geo is present, restore the geo route (backstop against the
            model negating an anchored term on 'looking for / husband finder / reverse'
            reasoning). If there is NO partner geo, GUARD3 does nothing — the generic negate
            stands, and no misleading flag is emitted.

  GUARD4  — UNCHANGED (coined/ethnic brand -> CAMPAIGN_PROTECT:source). Keep as-is.

Guards run 1->2->3 on every record; each is deterministic, cheap, logged, account-portable.
Interface: each guard takes (rec, inventory, idx) and a resolve_action(route, served) for the
"would this instance negate?" test. rec is a dict/obj with term, served_ad_group/ad_group_name,
route, confidence, level, flag, reason.
"""
import time

import config
import scope_router
from verticals.dating_geo.geo_anchor_map import build_anchor_index
from verticals.dating_geo.geo_gate import detect_geo, served_anchor_in_term


# ---- accessors (dict or object) --------------------------------------------------------
def _g(r, *names, default=None):
    for n in names:
        if isinstance(r, dict):
            if n in r:
                return r[n]
        elif hasattr(r, n):
            return getattr(r, n)
    return default

def _set(r, name, val):
    if isinstance(r, dict):
        r[name] = val
    else:
        setattr(r, name, val)

def _served(r):
    return _g(r, "served_ad_group", "ad_group_name")


# ---- shared geo helpers ----------------------------------------------------------------
_NON_DEST = {"_ORPHAN_", "_ESCALATE_", "_ORIGIN_", "_GEN_", "_LANG_", None}
LATIN_CAMPAIGN_BRANDS = {"chispa"}

def distinct_partner_geos(term, idx):
    """Set of concrete partner-geo destinations named in the term (country/general/
    sub-region/ccTLD groups). Excludes origin, language, orphan, and ambiguous placeholders."""
    dests = set()
    for tok, kind, dest in detect_geo(term, idx).hits:
        if kind in ("target", "general", "subregion", "tld") and dest not in _NON_DEST:
            dests.add(dest)
    return dests


GENDER_POLICY_CUES = (
    "looking for", "husband finder", "wife finder", "seeking foreign", "seeking american",
    "seeking western", "want western", "want foreign", "reverse", "reverse-gender",
    "reverse gender", "audience", "gaijin",
)

def _reason_is_gender_policy(reason):
    r = (reason or "").lower()
    return any(c in r for c in GENDER_POLICY_CUES)


# ---- GUARD 1 (demoted to telemetry) ----------------------------------------------------
def guard_served_country_wins(rec, inventory, idx):
    """Telemetry only. The gate (served_anchor_in_term) now enforces this. We annotate when a
    term names its own served group so shadow logs keep the signal, but we do NOT rewrite the
    route — enforcement is the gate's escalate path, which lets Sonnet adjudicate edges
    (bumble<country>, asian<lifestyle>) instead of a guard hard-overriding them."""
    if served_anchor_in_term(_served(rec), _g(rec, "term"), idx):
        prev = _g(rec, "flag", default="") or ""
        note = "GUARD1/telemetry: term names served group (enforced by gate)"
        _set(rec, "flag", (prev + " | " + note).strip(" |") if prev else note)
    return rec


# ---- GUARD 2 (fixed: dual-anchor only; collision fixed in geo_gate) --------------------
def guard_dual_anchor_keep(rec, inventory, idx, resolve_action):
    """Deterministic keep for the genuine DUAL-anchor case only. Fires when, for THIS served
    instance, the route would NEGATE, the served group's own target anchor is present, AND a
    second distinct partner geo is also named (so the term legitimately belongs in two groups,
    e.g. 'russian women in phuket' in Thailand). Sets force_keep_in -> scope_router keeps.
    Single own-anchor terms are intentionally left to the gate (escalate -> Sonnet)."""
    ag, term = _served(rec), _g(rec, "term")
    if resolve_action(_g(rec, "route"), ag) != "NEGATE":
        return rec
    if not served_anchor_in_term(ag, term, idx):
        return rec
    others = distinct_partner_geos(term, idx) - {ag}
    if others:                                           # dual-anchor confirmed
        _set(rec, "force_keep_in", ag)
        prev = _g(rec, "flag", default="") or ""
        note = f"GUARD2 keep in {ag} (dual-anchor: served anchor + {sorted(others)})"
        _set(rec, "flag", (prev + " | " + note).strip(" |") if prev else note)
    return rec


# ---- GUARD 3 (fixed: restore-geo only; no misleading NOOP) -----------------------------
def guard_quarantine_invented_policy(rec, inventory, idx):
    """Backstop against the model inventing gender/audience policy to negate an ANCHORED term.
    If a NEGATE_ALL is justified by 'looking for / husband finder / reverse / gaijin' reasoning
    AND a partner geo is present, restore the partner route (force keep). If there is NO partner
    geo, do nothing — the generic negate is correct and no flag is emitted (fixes the run-4
    'flag says NOOP but action is NEGATE' defect)."""
    if _g(rec, "route") != "NEGATE_ALL" or not _reason_is_gender_policy(_g(rec, "reason")):
        return rec
    partner = sorted(distinct_partner_geos(_g(rec, "term"), idx))
    if partner:
        dest = partner[0]
        _set(rec, "route", dest)
        _set(rec, "confidence", max(float(_g(rec, "confidence", "score", default=0.0) or 0.0), 0.8))
        prev = _g(rec, "flag", default="") or ""
        note = f"GUARD3 restore {dest} (receptivity framing, not a negate reason)"
        _set(rec, "flag", (prev + " | " + note).strip(" |") if prev else note)
    # else: no partner geo -> generic negate stands, no action, no flag.
    return rec


# ---- GUARD 4 (brand protect — coined/ethnic brand keeps its served campaign) -----------
def guard_brand_protect(rec, inventory, idx):
    """If Haiku tagged the term a coined/ethnic brand (level == 'brand_compound') but routed
    it somewhere that would negate it from its served campaign, normalize the route to
    CAMPAIGN_PROTECT:source. We negate ethnic/coined brands by hand, never automatically; this
    is the deterministic enforcement of that policy (fixes the run-3 'naomidate forced to
    Slavic then negated' bug). Brand RECOGNITION stays the model's job (doctrine brand-shape
    test); this only enforces protection once a term is recognized as a brand. Fused GEO-anchor
    brands (koreadates, asiacharm) are level country/general, not brand_compound, so they are
    untouched and route on their anchor."""
    if _g(rec, "level") == "brand_compound" and _g(rec, "route") != "CAMPAIGN_PROTECT:source":
        prev = _g(rec, "flag", default="") or ""
        note = f"GUARD4 {_g(rec, 'route')}->CAMPAIGN_PROTECT:source (coined brand protects served campaign)"
        _set(rec, "route", "CAMPAIGN_PROTECT:source")
        _set(rec, "flag", (prev + " | " + note).strip(" |") if prev else note)
    return rec


def guard_latin_campaign_brand(rec, inventory, idx):
    """Chispa is a Latin/Latino dating brand; keep it inside Latin-Search."""
    term = (_g(rec, "term") or "").lower()
    if any(brand in term for brand in LATIN_CAMPAIGN_BRANDS):
        if _g(rec, "route") != "CAMPAIGN_PROTECT:Latin-Search":
            prev = _g(rec, "flag", default="") or ""
            note = f"GUARD4 {_g(rec, 'route')}->CAMPAIGN_PROTECT:Latin-Search (Latin campaign brand)"
            _set(rec, "route", "CAMPAIGN_PROTECT:Latin-Search")
            _set(rec, "level", "brand_compound")
            _set(rec, "flag", (prev + " | " + note).strip(" |") if prev else note)
    return rec


# ---- runner ----------------------------------------------------------------------------
def run_guards(rec, inventory, idx, resolve_action):
    """Apply guards in order: GUARD4 (brand normalize) -> GUARD1 (telemetry) ->
    GUARD2 (dual-anchor keep) -> GUARD3 (gender-policy backstop)."""
    rec = guard_brand_protect(rec, inventory, idx)                   # coined brand -> protect
    rec = guard_latin_campaign_brand(rec, inventory, idx)            # Latin brand -> Latin campaign
    rec = guard_served_country_wins(rec, inventory, idx)             # telemetry
    rec = guard_dual_anchor_keep(rec, inventory, idx, resolve_action)  # dual-anchor keep
    rec = guard_quarantine_invented_policy(rec, inventory, idx)      # gender-policy backstop
    return rec


def run(rows: list[dict], inventory: dict[str, str]) -> list[dict]:
    """Repo pipeline adapter: apply package guards to a list of classified rows."""
    t0 = time.time()
    idx = build_anchor_index(inventory)
    resolve_action = scope_router.make_resolver(inventory, config.load_account_config())
    guarded = []
    fired = 0
    for row in rows:
        updated = dict(row)
        before = updated.get("flag")
        updated = run_guards(updated, inventory, idx, resolve_action)
        if updated.get("flag") and updated.get("flag") != before:
            fired += 1
        guarded.append(updated)
    elapsed = time.time() - t0
    print(f"Stage 5b — guards: {fired} guard signal(s) (in {elapsed:.1f}s)")
    return guarded

"""
geo_gate.py
===========
Deterministic geo-token detector and the gate rule that replaces "confidence >= HIGH
licenses any Haiku decision" with "confidence licenses a Haiku KEEP, but a Haiku NEGATE
is only allowed when the term carries NO target/ambiguous geo token."

The detector answers ONE question: does this term carry a partner-geo signal (resolved,
ambiguous, foreign-language, or fused) — as opposed to being pure generic / mainstream /
origin-only? It does NOT route. Routing stays with the model. The detector only decides
who is allowed to negate.

Verdict.geo_bearing == True  => Haiku may NOT negate this term; defer to Sonnet.
Verdict.geo_bearing == False => term is generic/origin-only; a Haiku NEGATE is trustworthy.
"""
import re
import unicodedata
from dataclasses import dataclass, field


def _norm(s):
    """Lowercase + strip diacritics so 'mötesplatsen'->'motesplatsen', 'españa'->'espana'."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


@dataclass
class Verdict:
    geo_bearing: bool
    hits: list = field(default_factory=list)   # [(token, kind, dest)] for telemetry/reason
    origin_only: bool = False

    @property
    def reason(self):
        if not self.hits:
            return "no geo token"
        kinds = ", ".join(sorted({k for _, k, _ in self.hits}))
        toks = ", ".join(sorted({t for t, _, _ in self.hits}))
        return f"{kinds}: {toks}"


def _present(stem, term):
    """Stem present at a word boundary, OR fused at a token start where the trailing tail is
    a plural ('asians'), a dating-glue word ('koreadates'), or plural+glue ('japansdates').
    Blocks mid-word false hits (india != indiana, china != chinatown)."""
    if " " in stem:                       # multiword: plain substring is safe/distinctive
        return stem in term
    for m in re.finditer(r'(?<![a-z])' + re.escape(stem) + r'([a-z]*)', term):
        tail = m.group(1)
        if tail == "" or tail in ("s", "es"):
            return True                   # exact token or simple plural: korea | asians
        t2 = tail[1:] if tail[:1] == "s" else (tail[2:] if tail[:2] == "es" else tail)
        if tail in _GLUE_CACHE or t2 in _GLUE_CACHE:
            return True                   # fused + glue (+optional plural): koreadates, japansdates
    return False


_GLUE_CACHE = set()


def _standalone(code, term):
    """ccTLD / language code used as a TLD signal: the FIRST or LAST token ('de dating sites',
    'neu de'), or a dotted form ('.de'). NOT interior — interior bare 'de'/'se' is almost
    always a Romance preposition ('paginas de citas', 'dil se dating'), not Germany/Sweden.
    term is already space-padded and normalized."""
    toks = term.split()
    if not toks:
        return False
    return toks[0] == code or toks[-1] == code or ("." + code) in term


def detect_geo(term, idx):
    """Return a Verdict. idx = build_anchor_index(inventory)."""
    global _GLUE_CACHE
    _GLUE_CACHE = idx["glue"]
    t = " " + _norm(term).strip() + " "
    hits = []

    # 1. foreign-language dating signal
    for w in idx["foreign"]:
        if _present(w, t):
            hits.append((w, "foreign", "_LANG_"))

    # 2. general phrases first (latin american / eastern european) then general stems
    for p in idx["general_phrases"]:
        if p in t:
            hits.append((p, "general_phrase", "_GEN_"))
    for s, dest in idx["general"].items():
        if _present(s, t):
            hits.append((s, "general", dest))

    # 3. sub-region words
    for s, dest in idx["subregion"].items():
        if _present(s, t):
            hits.append((s, "subregion", dest))

    # 4. target country / demonym / city / orphan demonym
    for s, dest in idx["target"].items():
        if _present(s, t):
            hits.append((s, "target", dest))

    # 5. homonyms — ambiguous unless an origin cue resolves them in-term
    for h in idx["homonyms"]:
        if _present(h, t):
            if any(_present(c, t) for c in idx["origin_cues"]):
                hits.append((h, "homonym_origin", "_ORIGIN_"))   # resolved -> origin
            else:
                hits.append((h, "ambiguous", "_ESCALATE_"))

    # 5b. standalone ccTLD / language code (.de, "neu de") -> target/foreign geo signal
    for code, dest in idx.get("tld", {}).items():
        if _standalone(code, t):
            hits.append((code, "tld", dest))

    # 6. origin tokens (only matters for the origin_only flag)
    origin_hit = any(_present(o, t) for o in idx["origin"])

    # geo-bearing if ANY target / general / subregion / foreign / ambiguous / tld signal.
    routing_kinds = {"foreign", "general", "general_phrase", "subregion", "target",
                     "ambiguous", "tld"}
    geo_bearing = any(k in routing_kinds for _, k, _ in hits)

    # origin_only: origin present (token or resolved homonym) and nothing routing.
    resolved_origin = origin_hit or any(k == "homonym_origin" for _, k, _ in hits)
    origin_only = resolved_origin and not geo_bearing
    return Verdict(geo_bearing=geo_bearing, hits=hits, origin_only=origin_only)


from verticals.dating_geo.geo_anchor_map import own_anchor_stems


def served_anchor_in_term(served_ag, term, idx):
    """True if the term contains the SERVED ad group's OWN anchor (its demonym/name/city/
    region, or its general/sub-region word, or its standalone ccTLD). This is the
    false-negate signature: negating a term that names the very group it was served in
    (china in China, dublin in Ireland, asian in Asia, haitian in Haiti, ' de ' in Germany).
    GUARD1 generalized to every level, expressed as a gate trigger."""
    t = " " + _norm(term).strip() + " "
    stems = set(own_anchor_stems(served_ag))
    # Slavic precedence (doctrine special_case): 'eastern european' is the Slavic sphere,
    # never the Asian 'Eastern' orphan bucket. Don't let bare 'eastern' anchor Eastern(Asia)
    # when the term says 'eastern europe(an)'. (Fixes the GUARD2 substring collision.)
    if served_ag == "Eastern" and ("eastern europe" in t or "eastern european" in t):
        stems.discard("eastern")
    if any(_present(s, t) for s in stems):
        return True
    for code, dest in idx.get("tld", {}).items():
        if dest == served_ag and _standalone(code, t):
            return True
    return False


# --------------------------------------------------------------------------------------
# THE GATE RULE  (sharp own-anchor variant — the validated design)
# --------------------------------------------------------------------------------------
HIGH = 0.85

def route_decision(rec, idx, served_ag, guard_flagged=False, protected_brand=False):
    """Returns 'apply' or 'escalate'.
       - Haiku KEEP at >=HIGH                                  -> apply (cheap, safe)
       - Haiku NEGATE at >=HIGH, not brand, term does NOT name -> apply (no-geo junk OR a
         its own served group                                          clean cross-negation)
       - Haiku NEGATE where the term NAMES its served group    -> escalate (false-negate sig)
       - low-conf / brand-ambiguous / guard-flagged            -> escalate
    Correct cross-negations (anchor points to a DIFFERENT existing group) stay on Haiku;
    only own-group-naming negates and brand-ambiguous calls reach the keep-biased Sonnet,
    whose bias is now aligned with the escalated set (these should usually be kept)."""
    if guard_flagged:
        return "escalate"
    action, conf = rec_action(rec), rec_conf(rec)
    if action == "KEEP" and conf >= HIGH:
        return "apply"
    if (action == "NEGATE" and conf >= HIGH and not protected_brand
            and not served_anchor_in_term(served_ag, rec_term(rec), idx)):
        return "apply"
    return "escalate"


# tiny accessors so this works against dicts or objects
def rec_term(r):   return r["term"]   if isinstance(r, dict) else r.term
def rec_action(r): return r.get("action") if isinstance(r, dict) else getattr(r, "action", None)
def rec_conf(r):
    if isinstance(r, dict):
        v = r.get("confidence", r.get("score"))
    else:
        v = getattr(r, "confidence", getattr(r, "score", None))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

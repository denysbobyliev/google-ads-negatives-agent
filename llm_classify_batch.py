from __future__ import annotations
"""
Stage 6: LLM Classification
Groups PASS terms by region, batches them, calls Claude, parses JSON.
Retry logic: on parse failure, re-ask once with stricter "JSON only" reminder.
Second failure: log to logs/llm_failures.jsonl and skip.
"""

import json
import os
import sys
import time
from itertools import groupby

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import config
from llm_logger import log_llm_failure

SYSTEM_TEMPLATE = """\
You score Google Ads search terms for a campaign whose sole purpose is helping \
men find and date women from: {target_region_label}.

Every term in this list already comes from a dating-related search — assume \
dating intent. Do NOT score based on whether the term "sounds like dating." \
Score based on ONE question only:

  Is the person searching this term looking for women from {target_region_label}?

An earlier regex pass already confirmed the term matches none of these known \
regional anchors:
{all_anchor_universe_joined}

--- AD GROUP ROLE ---
{archetype_context}
{region_notes}
--- SCORING RULES ---

Score guide (1–10):
  9–10  Strong geographic match — any of:
        • Country name, nationality ADJECTIVE, or PLURAL DEMONYM for the target region.
          Plural demonyms are equivalent to the adjective: "Asians" = "Asian",
          "Russians" = "Russian", "Ukrainians" = "Ukrainian", "Latinas" = "Latina".
          Do NOT treat a language name as a match unless identical or nearly identical
          to the adjective (español/espanol = Spanish = OK; Mandarin ≠ Chinese).
        • Sub-region, state, province, island, city, or area within the target country
          (Bavaria→Germany, Catalonia→Spain, Sicily→Italy, Hokkaido→Japan, etc.)
        • Dating site or brand whose primary focus is connecting users with people from
          the target country/region — score by the brand's focus, not by recognition.
          Well-known examples: UkraineDate/UkrainianCharm/uadreams → Ukraine;
          RussianCupid/ruswife → Russia; AnastasiaDate → Slavic; Meetic → France;
          VictoriaHearts/victoria hearts → Slavic/Eastern European.
        • Partial/abbreviated brand names that clearly point to a known regional site
          (ukrcharm → UkrainianCharm, sofiadate → SofiaDate, etc.)
        User-location modifiers — "near me", "in london", "in canada", country
        codes (uk, us, ca, au, nz) and navigation words (login, sign up, review,
        app, scam, legit, is it real, how to) — NEVER reduce the score when a
        regional signal is already present. They only tell you where the user is
        sitting, not what kind of partner they want.
        Rule: if the term already contains a word that matches the target region
        (country name, demonym, brand, or culturally-specific word), ignore any
        user-location modifier entirely. Score on the regional signal alone.
  7–8   Moderate geographic connection — any of:
        • Indirect cultural reference, historical term, regional lifestyle, or
          demonym clearly and specifically associated with the target area but
          not the country name itself
        • An unfamiliar brand or site name that contains a word, morpheme, or
          phonetic pattern recognisably from the target region's primary language —
          even if you cannot confirm the brand exists. Reasoning: in a dating-ads
          context, a brand using target-language vocabulary almost certainly targets
          that audience. Score 7–8, not 1–3, when in doubt.
          Examples: "mariadate" → Ukraine/Slavic; "katiasingles" → Russia/Slavic;
          "amorlatina" → Latin America; a name with Polish morphology → Poland.
        • A brand name that BEGINS WITH or CONTAINS a known regional anchor word,
          even when the anchor and the rest of the name are concatenated without a
          space. Do NOT require a word boundary inside a compound brand name.
          Examples: "asianmatchmate" starts with "asian" → score 9 for Asia;
          "asiansouls", "asianfeels", "asiandati" → same logic. The anchor is
          still there — it is just joined to the rest of the brand name.
        • A word in the query that is CULTURALLY SPECIFIC to the target region's
          language — meaning the word is distinctly associated with that culture
          and would not appear in a generic English dating search.
          IMPORTANT DISTINCTION — only culturally-specific words qualify:
            QUALIFIES: "randki" (distinctly Polish word for romantic dates, no
              cross-language equivalent) → score 8 for Poland
            DOES NOT QUALIFY: "site de rencontre" (= "dating site" in French —
              it is a generic term that merely happens to be in French; treat it
              exactly like "best dating site" in English → score 1–3)
            DOES NOT QUALIFY: "incontri" (= "meetings/dates" in Italian — generic),
              "Partnervermittlung" (= "matchmaking" in German — generic)
          The test: could this word appear in a generic English dating ad with a
          direct translation and mean exactly the same thing? If yes, it is generic
          and scores low. If it is a culture-specific term with no clean English
          equivalent, it scores 7–8.
          User-location modifiers do not change this: "randki uk" still scores 8
          for Poland — "uk" only tells you the user is in the UK, not that they
          want British women.
  5–6   Borderline: some geographic hint but genuinely ambiguous — use sparingly
  1–3   No geographic signal OR wrong region/niche:
        • Generic dating queries with zero connection to the target region, whether
          in English OR translated into any other language — cap at 3.
          ("local dating sites", "best dating app", "find women online",
          "meet girls near me", "top dating sites", "site de rencontre",
          "incontri online", "Partnervermittlung") — all generic, all score ≤ 3
        • Terms explicitly naming a different country, region, or a demographic/
          religious niche that implies a different product
          ("jewish dating" in CEE, "english dating" in Russia, "iraqi women" in Europe)
        • User-location language alone ("near me", "in london", "au", "nz") with
          no regional word is NOT a signal — score ≤ 3

Score ≥ 6 → KEEP. Score < 6 → NEGATE at ad group level.

Return a strict JSON array, one object per input term:
{{"term": "<input term lowercase>", "score": <1-10 integer>, "anchor": "<what you found, or null>", "reason": "<one short sentence>"}}

No preamble, no markdown fences, no commentary. JSON array only.\
"""

RETRY_REMINDER = (
    "Your previous response could not be parsed as JSON. "
    "Return ONLY a valid JSON array — no preamble, no markdown, no commentary."
)

_ARCHETYPE_CONTEXT = {
    # Pan-regional group (e.g. "Asia", "Latina")
    # Owns the broad demonym. Specific countries route to their own groups.
    "pan_regional_demonym": """\
This is the BROAD REGIONAL ad group — it captures users searching for women \
from this region in general, not from a specific country within it.

  KEEP  — term signals the broad region (e.g. "Asian", "Latina") with no \
more-specific country reference, OR is a brand operating at this broad \
regional level (e.g. "AsiaFeels", "EasternHoneys").
  NEGATE — term contains BOTH the broad regional signal AND a specific \
country within the region (e.g. "Asian Korean women", "Asian Japanese dating") \
— those users want a specific country and belong in that country's ad group.
  NEGATE — term names a specific country with no broad regional anchor — \
belongs in that country's ad group.""",

    # Dedicated single-country group (e.g. Japan, Korea, Poland, France)
    # Owns country-specific signals. Also owns "broad + this country" combos.
    "hero_country": """\
This is a SINGLE-COUNTRY ad group — it captures users specifically interested \
in women from {target_region_label}.

  KEEP  — term has this country's specific signal (country name, demonym, city, \
cultural reference, brand focused on this country).
  KEEP  — term combines a broad regional anchor ("Asian", "Slavic", "European") \
WITH this country's specific signal — e.g. "Asian dating Korean women", \
"Slavic Polish ladies" — the user has narrowed to this specific country.
  NEGATE — term carries ONLY a broad regional signal ("Asian", "Slavic") with \
NO country-specific element — belongs in the broad regional ad group.
  NEGATE — term names a DIFFERENT country in the same region.""",

    # Small-country catch-all (e.g. "Asian Countries", "LATAM Countries")
    # Owns smaller-country signals. Also owns "broad + small country" combos.
    # Generic pan-regional terms belong to the pan_regional_demonym group.
    "catch_all": """\
This is the SMALL-COUNTRY CATCH-ALL ad group — it captures users searching for \
women from smaller or less-searched countries within the region (countries that \
do not have their own dedicated ad group).

  KEEP  — term signals one of these smaller countries (country name, demonym, \
city, cultural reference, brand focused on this country).
  KEEP  — term combines a broad regional anchor ("Asian", "Latina") WITH a \
specific smaller country — e.g. "Asian Mongolian women", "Asian Cambodian dating".
  NEGATE — term has ONLY the broad regional signal ("Asian", "Latina") with NO \
country reference — belongs in the broad regional ad group.
  NEGATE — term names a hero country that has its own dedicated group.""",

    # Hybrid: acts as both pan-regional AND small-country catch-all
    # (e.g. "Euro Countries", "CEE Countries")
    # Owns: generic European/Slavic searches + non-hero country searches.
    # Hero countries (Poland, Russia, Germany, France, etc.) have their own groups.
    "hybrid": """\
This is a HYBRID ad group — it serves two purposes at once:
  (a) Pan-regional: captures generic European/Slavic/regional searches where \
the user has not specified a particular country.
  (b) Catch-all: captures searches for smaller countries in this region that \
do not have their own dedicated ad group.

  KEEP  — term signals this region broadly (e.g. "European women", \
"Slavic dating", "Eastern European ladies") with no specific hero-country name.
  KEEP  — term signals a smaller/non-hero country within this region.
  KEEP  — term combines a broad regional anchor WITH a smaller/non-hero country.
  NEGATE — term specifically names a hero country that has its own ad group \
(e.g. Poland, Russia, Ukraine, Germany, France, Romania, Czech, etc.).""",
}


def _build_archetype_context(region: dict) -> str:
    archetype = region.get("archetype", "hero_country")
    template = _ARCHETYPE_CONTEXT.get(archetype, _ARCHETYPE_CONTEXT["hero_country"])
    return template.format(target_region_label=region["target_region_label"])


def _build_system_prompt(region: dict, all_anchors: set[str]) -> str:
    all_anchor_str = ", ".join(sorted(all_anchors)) if all_anchors else "(none)"
    notes = region.get("region_notes", "")
    region_notes_block = f"NOTE: {notes}\n" if notes else ""
    return SYSTEM_TEMPLATE.format(
        target_region_label=region["target_region_label"],
        archetype_context=_build_archetype_context(region),
        region_notes=region_notes_block,
        all_anchor_universe_joined=all_anchor_str,
    )


def _call_llm(client: anthropic.Anthropic, system: str, user_msg: str) -> anthropic.Message:
    return client.messages.create(
        model=config.MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )


def _parse_response(text: str) -> list[dict] | None:
    text = text.strip()
    # Strip markdown fences if the model disobeyed
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return None


def _classify_batch(
    client: anthropic.Anthropic,
    region: dict,
    batch_terms: list[str],
    all_anchors: set[str],
) -> tuple[list[dict], list[str]]:
    """
    Returns (classified_objects, failed_terms).
    failed_terms were not parseable even after one retry.
    """
    system = _build_system_prompt(region, all_anchors)
    user_msg = "Classify:\n" + "\n".join(batch_terms)

    msg = _call_llm(client, system, user_msg)
    result = _parse_response(msg.content[0].text)

    if result is None:
        # Single retry with stricter reminder
        retry_messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": msg.content[0].text},
            {"role": "user", "content": RETRY_REMINDER},
        ]
        msg2 = client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            system=system,
            messages=retry_messages,
        )
        result = _parse_response(msg2.content[0].text)

    if result is None:
        return [], batch_terms

    # Reconcile: build term→result map, mark any missing as failures
    result_map = {r["term"].lower().strip(): r for r in result if isinstance(r, dict)}
    classified = []
    failed = []
    for term in batch_terms:
        if term in result_map:
            classified.append(result_map[term])
        else:
            failed.append(term)

    return classified, failed


def _load_regions_by_key() -> dict[str, dict]:
    import yaml
    with open(config.REGIONS_YAML) as f:
        return yaml.safe_load(f)["regions"]  # already keyed by region_key


def run(
    llm_candidates: list[dict],
    all_anchors: set[str],
) -> tuple[list[dict], int, float]:
    """
    Returns (classified_terms, llm_calls_made, estimated_cost_usd).
    classified_terms have llm_decision, llm_confidence, llm_anchor, llm_reason added.
    """
    t0 = time.time()
    if not llm_candidates:
        print("Stage 6 — llm_classify_batch: 0 terms, skipped")
        return [], 0, 0.0

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    regions_by_key = _load_regions_by_key()

    # Group candidates by region_key
    candidates_by_region: dict[str, list[dict]] = {}
    for t in llm_candidates:
        candidates_by_region.setdefault(t["region_key"], []).append(t)

    term_meta = {t["term"]: t for t in llm_candidates}  # for attaching results back

    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    classified_count = 0
    failed_count = 0

    for rk, cands in candidates_by_region.items():
        region = regions_by_key[rk]
        terms_for_region = [c["term"] for c in cands]

        for i in range(0, len(terms_for_region), config.LLM_BATCH_SIZE):
            batch = terms_for_region[i : i + config.LLM_BATCH_SIZE]
            classified, failed = _classify_batch(client, region, batch, all_anchors)
            total_calls += 1
            if failed:
                for term in failed:
                    total_calls += 1  # the retry counted
                    log_llm_failure(term, rk)
                    failed_count += 1

            for obj in classified:
                term = obj.get("term", "").lower().strip()
                if term in term_meta:
                    t = term_meta[term]
                    t["llm_score"] = int(obj.get("score", 5))
                    t["llm_anchor"] = obj.get("anchor")
                    t["llm_reason"] = obj.get("reason", "")
                    classified_count += 1

    # Any candidate not touched by LLM (parse failures already logged) → skip
    result = [t for t in llm_candidates if "llm_score" in t]

    estimated_cost = (
        total_input_tokens / 1000 * config.LLM_COST_PER_1K_INPUT_TOKENS
        + total_output_tokens / 1000 * config.LLM_COST_PER_1K_OUTPUT_TOKENS
    )

    elapsed = time.time() - t0
    print(
        f"Stage 6 — llm_classify_batch: {classified_count} classified, "
        f"{failed_count} parse failures, {total_calls} API calls "
        f"(in {elapsed:.1f}s)"
    )
    return result, total_calls, estimated_cost

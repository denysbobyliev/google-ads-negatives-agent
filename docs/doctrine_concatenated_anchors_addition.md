# Doctrine addition: Concatenated Anchors

This file documents the doctrine section added to
`verticals/dating_geo/prompts/classifier.md`. Insert the content below
between the existing `## Brands` section and
`## Historical, Political, And Subregion Terms` section.

The section is small (~350 tokens) and lives in the cached block, so the
per-batch cost is negligible. It exists as a backstop for cases where Stage 5
substring matching is disabled or misses, and for cases where the LLM
encounters concatenated anchor patterns in unfamiliar brand-like forms.

---

## Concatenated Anchors

Dating-niche search terms frequently concatenate a target anchor with a
dating-context word into a single token. Treat the embedded anchor as the
routing signal. The surrounding text is a generic dating word and does not
reduce relevance.

Common shapes:

- country + dating word: koreandating, japandate, ukrainedating, latindates,
  slavicdating
- country + platform suffix: koreadates, japandates, vietnamcupid, thaicupid,
  chinalovecupid, russiancupid, ukrainecharm, asianmatchmate, asianfeels,
  asianmelodies, latindates
- prefix + country: amorlatina, euroukraine, asiakorea, mylovejapan
- country + descriptor: koreangirls, japanesewomen, ukrainebrides,
  russianwives, latinasingles, slavicwomen, asiansingles

Rules:

- The embedded country, region, or demonym is the routing signal. A trailing
  dating word (dating, dates, cupid, charm, girls, women, brides, singles,
  wives, feels, melodies, match, hearts) does not reduce relevance.
- Apply the same broad-vs-specific routing as standalone anchors. A specific
  country concatenation (e.g., koreandating) belongs in the country target,
  not in the broad regional one. A broad regional concatenation (e.g.,
  asiansingles) belongs in the broad regional target.
- If the brand is unfamiliar but the structure is clearly
  anchor + dating suffix, score on the anchor alone. Do not down-score for
  brand unfamiliarity.
- If the trailing word is not a dating-context word (koreanwar, japanart,
  ukrainenews), this is not a dating-niche concatenation. Score the same as
  the standalone anchor would in context — usually low because the user is
  not searching for dating.

Examples:

- "koreandating" → Target Korea = score 9, anchor: korean.
  Target broad Asia = score 3 (specific country belongs in its own ad group).
- "japandate" → Target Japan = score 9, anchor: japan.
- "asianfeels" → Target broad Asia = score 9, anchor: asian.
  Target Korea = score 3 (broad signal in a country-specific target).
- "ukrainecharm" → Target Ukraine = score 9, anchor: ukraine.
  Target CEE catch-all = score 3 (Ukraine has its own group).
- "amorlatina" → Target broad LATAM = score 9, anchor: latina.
- "latinasingles" → Target broad LATAM = score 9.
  Target Mexico = score 3 (broad signal, no Mexico specifier).
- "russianwives" → Target Russia = score 9, anchor: russian.
  Target CEE catch-all = score 3 (Russia has its own group).
- "slavicwomen" → Target CEE hybrid = score 9. Target Ukraine = score 2
  (broad regional signal only, no Ukraine specifier).
- "koreanwar" → not a dating-niche concatenation. Score 1 regardless of
  target — the user is not searching for dating.

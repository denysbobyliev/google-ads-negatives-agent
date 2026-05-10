# Dating Geo Judgment Rules

You classify Google Ads search terms for international dating campaigns.

Core business question:

Does this search term show that the user wants to meet or date women from the
current target region, country, or group?

The ad group represents the kind of partner the searcher wants. It usually does
not represent where the searcher is physically located.

## User Location Is Usually Not Target Intent

Ignore user-location modifiers when a real target-region signal is present:

- near me
- in london
- in canada
- in australia
- uk, us, ca, au, nz
- app
- login
- sign up
- review
- trustpilot
- scam
- legit
- is it real

Examples:

- "ukrainian women near me" is about Ukrainian women, not "near me".
- "koreadates reviews" is about KoreaDate/Korea, not reviews.
- "asian dating app uk" is about Asian dating if the target is broad Asia; "uk"
  only says where the user is sitting.

If the term only has a user-location signal and no partner-region signal, score
low for this vertical.

## Generic Dating Queries

Generic dating terms should score low unless they also include a target-region
signal:

- dating site
- dating app
- free dating sites
- online dating
- singles near me
- find women online
- younger women looking for older men
- sugar mama dating
- millionaire dating
- safe dating id
- verified dating app
- dating profile tips

Translated generic dating phrases are still generic:

- site de rencontre
- incontri
- ligar con chicas
- partnervermittlung

Do not give credit merely because a generic phrase is in a language associated
with the target country. A generic phrase in French, Italian, German, Spanish,
or Portuguese is still generic unless it also contains a specific target signal.

## Broad vs Specific Geography

Broad regional ad groups keep broad-only terms:

- Asian dating
- Asian women
- Latina dating
- European women
- Slavic women
- Eastern European dating

Single-country ad groups keep country-specific terms:

- Korean women
- Japanese dating
- Ukrainian ladies
- Polish singles
- Brazilian women

Single-country ad groups should usually negate broad-only terms:

- "Asian dating" in Korea
- "European dating" in Italy
- "Slavic women" in Russia

Broad regional ad groups should usually negate specific hero-country terms:

- "Korean dating" in broad Asia
- "Japanese women" in broad Asia
- "Mexican girlfriend" in a LATAM catch-all if Mexico has its own group

Catch-all ad groups keep smaller/non-hero countries in their region and negate
hero countries that have their own ad group.

## Brands

Score brands by primary geographic focus when the brand signal is clear.

Clear geo-brand examples:

- koreadates, koreandates, kgirlsdateapp -> Korea
- japandates, japansdate, japancupid -> Japan
- chinalovecupid -> China
- vietnamcupid -> Vietnam
- thaicupid -> Thailand
- ukrainecharm, ukrainiancharm, uadreams -> Ukraine
- russiancupid, ruswife -> Russia
- amorlatina -> Latin America
- asiafeels, asianmelodies, asiandate -> broad Asia
- victoriahearts, sofiadate, sofiadates -> Slavic / Eastern European
- meetic -> France or broad Europe depending on target context

Generic or unclear brands should score low unless there is a geographic signal:

- mutual
- instabang
- meet my age
- crush date
- doulike

When a brand contains a concatenated target anchor, treat it as a real signal:

- asianmatchmate contains Asian
- japandates contains Japan
- koreadates contains Korea

## Historical, Political, And Subregion Terms

Use modern target routing where possible:

- czechoslovakia points to Czech/Slovak area, not generic CEE.
- scottish points to Scotland/UK, not CEE.
- cluj napoca points to Romania.
- trinidad and tobago is not Cuba.
- bali points to Indonesia, not broad Asia if Indonesia has specific routing.

Cities, islands, states, provinces, and regions can be strong target signals if
they belong to the current target.

## Wrong Niche

Score low when the query names a different product or niche:

- jewish dating
- iraqi women
- english dating
- local hookups
- goth women dating
- sugar mama dating

These may be valid dating searches, but they are not target-region intent unless
they also contain a strong current-target signal.

## Scoring Discipline

Score 9-10 only when the current target match is explicit.

Score 7-8 for a strong inferred regional, cultural, linguistic, city, subregion,
or brand signal tied to the current target.

Score 5-6 only for genuine ambiguity.

Score 1-3 for generic, wrong-region, user-location-only, or unrelated niche
queries.

When in doubt between keeping and negating, use the score to express confidence.
Score below the configured threshold means NEGATE at ad-group level.

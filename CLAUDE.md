# CLAUDE.md — google-ads-negatives-agent

Architectural context for agents working in this repo.

## Purpose

Route-based Google Ads negative-keyword pipeline. It pulls search terms from
labeled ad groups, classifies each unique term to a single route with Claude,
converts that route into a served-ad-group action, writes a report, and can
upload exact-match negatives.

## Current Architecture

The old `targets.yaml` / anchor / per-region prompt layer is removed. Do not
reintroduce it.

The single customization surface is:

```text
verticals/dating_geo/prompts/classifier.md
```

The first fenced YAML block under `ACCOUNT BLOCK` is parsed by
`config.load_account_config()` and is also part of the cached LLM system prompt.
The live ad-group inventory is pulled at runtime and appended before the cache
breakpoint.

## Pipeline

```text
pull_scope.py          — labeled ad groups + live inventory
pull_search_terms.py   — search_term_view rows per served ad group
filter_by_cost.py      — spend filter and conversion-value protection
dedupe_cache.py        — served ad-group/term cache dedupe
classify_batch.py      — Agent 1, Haiku route classifier
guards.py              — deterministic corrections, fused-anchor keeps, source-brand normalization, and dual-anchor keep guards
confidence_gate.py     — send low-confidence/REVIEW/guarded rows to Sonnet
escalate.py            — Agent 2, terminal Sonnet classifier
scope_router.py        — route -> KEEP/NEGATE/NOOP per served ad group
dry_run_report.py      — CSV review report
upload_negatives.py    — exact-match AG/campaign negatives
update_cache.py        — append completed decisions
```

## Route Contract

Classifier output:

```json
{"term":"...","route":"...","level":"country|general|sub_region|brand_compound|language|none","confidence":0.0,"lang":null,"reason":"..."}
```

Supported route values:

- ad-group name: keep only in that ad group.
- `CAMPAIGN_PROTECT:<campaign>`: keep anywhere in that campaign.
- `CAMPAIGN_PROTECT:source`: keep in the campaign where it served.
- `LANG_KEEP:<lang>`: keep in countries and campaign generals from `language_map`.
- `NEGATE_ALL`: campaign-level negative for the served campaign.
- `REVIEW`: safe no-op.

## Eval And Porting

Golden fixture:

```text
verticals/dating_geo/eval/golden_set.csv
```

Run:

```bash
python3 eval_golden.py
```

For a new account, create a new ACCOUNT BLOCK, then run `relabel_golden.py`.
It carries account-independent rows over, re-proposes only geo-dependent rows
under the new inventory, and flags changed answers with `needs_review=CHANGED`.
Then append 50-80 high-cost account-specific terms and run the eval.

## Conventions

- Prompt doctrine belongs in `verticals/<vertical>/prompts/classifier.md`, not Python logic.
- Do not duplicate the ACCOUNT BLOCK into a separate config file.
- Do not use `targets.yaml`, `region_context.md`, `archetypes.yaml`, or regex anchors.
- Guard-corrected rows must still escalate to Sonnet for verification.
- Coined/ethnic dating brands normalize to `CAMPAIGN_PROTECT:source`; do not guess a target campaign from brand flavor.
- `force_keep_in` from `guards.py` wins in `scope_router.py` for dual-anchor served instances.
- Dry-run first; use `--shadow` before trusting live traffic.
- Do not touch `.env`, `google-ads.yaml`, `data/`, `logs/`, or generated reports unless explicitly asked.

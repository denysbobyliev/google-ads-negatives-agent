# CLAUDE.md — google-ads-negatives-agent

> Architectural and behavioral context for agents working in this repo.
> Global rules in `~/.claude/CLAUDE.md` apply unless overridden here.

## What this repo does
Profile-driven Google Ads negative-keyword pipeline. It pulls search terms from
labeled ad groups, classifies each term with regex anchors and LLM scoring, writes
a review report, and can upload EXACT-match negative keywords at ad-group level.

The committed profile `accounts/dating_main.yaml` is a placeholder template.
Real customer IDs, account labels, and credential paths belong in ignored local
profiles such as `accounts/<account_key>.local.yaml`.

Dry-run is the default. Dry-run never sends Google Ads mutations and does not
update the local cache unless `--write-cache` is passed.

## Architecture
```
Stage 1  pull_scope.py          — find labeled ad groups, resolve region_key
Stage 2  pull_search_terms.py   — pull search_term_view for scoped ad groups
Stage 3  filter_by_cost.py      — active / protected / below-threshold split
Stage 4  dedupe_cache.py        — skip cached account+vertical+region+term pairs
Stage 5  regex_anchor_check.py  — standalone/concatenated own_anchor → KEEP; sibling_anchor → NEGATE_AG
Stage 6  llm_classify_batch.py  — render vertical prompt, call Claude, parse JSON
Stage 7  confidence_gate.py     — score threshold from vertical policy
Stage 8  scope_router.py        — all NEGATE/DEFER routed to ad_group level
Stage 9  dry_run_report.py      — always writes reports/run_YYYY-MM-DD_HHMMSS.csv
Stage 10 upload_negatives.py    — skipped in dry-run; uploads EXACT AG negatives
Stage 11 update_cache.py        — live runs update cache after upload
```

## Repo Structure
```
.
├── accounts/
│   └── dating_main.yaml              # account/customer/labels/paths/profile
├── verticals/
│   └── dating_geo/
│       ├── policy.yaml               # thresholds, model, caps, scoring policy
│       ├── targets.yaml              # region/ad-group anchors and archetypes
│       └── prompts/
│           ├── classifier.md         # cacheable classifier doctrine
│           ├── region_context.md     # per-target LLM context template
│           └── archetypes.yaml       # archetype-specific prompt blocks
├── tools/
│   ├── remove_negatives.py
│   ├── inspect_anchor_patterns.py
│   └── validate_targets.py
├── tests/
├── run.py
├── config.py                         # compatibility bridge that loads profiles
├── target_loader.py
├── regions.yaml                      # legacy copy; prefer vertical targets
├── data/
├── logs/
└── reports/
```

## Key Files
- `run.py` — orchestrator and CLI entry point.
- `accounts/dating_main.yaml` — default account profile; customer ID, labels, Google Ads config path, output paths.
- `verticals/dating_geo/policy.yaml` — business thresholds, score cutoff, caps, model, LLM cost settings.
- `verticals/dating_geo/targets.yaml` — target groups, own anchors, sibling anchors, archetypes.
- `verticals/dating_geo/prompts/classifier.md` — cacheable vertical-specific classifier doctrine.
- `verticals/dating_geo/prompts/region_context.md` — per-target context rendered for each batch.
- `target_loader.py` — single loader for active target definitions.
- `data/classified_terms.json` — local dedupe cache; new writes include account/vertical/policy/prompt metadata.
- `tools/inspect_anchor_patterns.py` — debugging CLI for Stage 5 standalone and concatenation anchor matching.
- `tools/validate_targets.py` — validates target definitions before running.

## Conventions
- Account-specific settings belong in `accounts/<account_key>.yaml`.
- Vertical-specific policy belongs in `verticals/<vertical_key>/policy.yaml`.
- LLM prompt text belongs in `verticals/<vertical_key>/prompts/`, never inside Python logic.
- Target/ad-group/anchor relationships belong in `verticals/<vertical_key>/targets.yaml`.
- `regions.yaml` is legacy compatibility data. Do not add new target data there unless deliberately maintaining the old copy too.
- Pipeline defaults to dry-run. `--no-dry-run` is required to upload.
- Dry-run is locally read-only by default. Use `--write-cache` only when you intentionally want to persist classifications from a dry run.
- All automatic negations currently go to ad-group level only; `campaign_level` exists for future policy work but is not populated automatically.
- Accent normalization is applied at anchor compile time and match time; accented and unaccented duplicate anchors collide.

## Stage 5 — Concatenation Matching
Stage 5 first checks standalone word-boundary anchors. If no standalone anchor
matches, it checks eligible anchors as plain substrings inside whitespace tokens
to catch dating forms like `koreandating`, `japandates`, `ukrainecharm`, and
`amorlatina`.

Concatenation matching uses the same shortcut routing as standalone matching:
own-anchor substring matches are `KEEP`; sibling-anchor substring matches are
`NEGATE_AG`. Match audit fields include `match_type`, `matched_anchor`,
`match_origin`, and, for substring matches, `containing_token`.

Controls live in `verticals/<vertical_key>/policy.yaml` under `concatenation`:
- `enabled` disables the substring layer when set to `false`.
- `min_anchor_length` keeps short anchors such as `uk` word-boundary only.
- `exclude_within` suppresses known full-token collisions for a specific anchor,
  for example `asian: [caucasian, caucasians]`.

Populate `exclude_within` reactively from run audits when a substring match is
valid as text containment but wrong for routing. After editing it, run:
```bash
python3 tools/validate_targets.py
python3 tools/inspect_anchor_patterns.py --region asia_pan --test-term "caucasian women"
```

## Gotchas
- `.env`, `google-ads.yaml`, and `accounts/*.local.yaml` are intentionally ignored by Git. Do not commit credentials, IDs, OAuth tokens, account labels, or API keys.
- `--ignore-cache` is only allowed with `--dry-run`.
- Score-3 terms are deferred when policy says so; deferred terms are excluded from cache updates so they resurface next run.
- Always run target validation after editing target anchors:
  ```bash
  python3 tools/validate_targets.py
  ```
- Use strict sibling validation only when intentionally converting sibling anchors to a fully derived all-other-targets set:
  ```bash
  python3 tools/validate_targets.py --strict-siblings
  ```
- The local system Python is currently 3.9 and emits Google client warnings. Prefer a managed Python 3.10+ environment when stabilizing deployment.

## How To Run
```bash
# Validate config/targets
python3 tools/validate_targets.py
python3 -m unittest discover -s tests

# Dry run — default account profile
python3 run.py --dry-run --days 30

# Dry run — single region
python3 run.py --dry-run --days 30 --region ukraine

# Re-evaluate cached terms without writing cache
python3 run.py --dry-run --days 30 --ignore-cache

# Dry run and intentionally persist classifications to local cache
python3 run.py --dry-run --days 30 --write-cache

# Go live after reviewing reports/
python3 run.py --no-dry-run --days 30
```

## Before Adding A New Account Or Vertical
Use `docs/new_account_or_vertical.md`. The intended swap points are:
- account profile
- policy file
- target/anchor file
- classifier prompt
- credentials path

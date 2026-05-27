# Google Ads Negatives Agent

Profile-driven Google Ads negative-keyword pipeline for international dating campaigns.

The current architecture is route-based. The classifier makes one decision per search
term: which ad group, campaign zone, language zone, or global negative bucket the term
belongs to. The router then compares that route to the ad group where Google served the
term and decides `KEEP`, `NEGATE`, or `NOOP`.

There are no hand-maintained target anchors, `region_key`s, or per-ad-group prompts.
The live ad-group inventory is pulled from Google Ads and injected into the shared
classifier doctrine at runtime.

## Safety

The pipeline defaults to dry-run:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30
```

Dry-run pulls real Google Ads data, can call Anthropic, writes a report, and uploads
nothing. Live upload requires:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --no-dry-run --days 30
```

Shadow mode runs classification/routing against live traffic and writes
`logs/shadow_<date>.csv`, but uploads nothing:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --shadow --days 30
```

## Pipeline

| Stage | File | Responsibility |
|---:|---|---|
| 1 | `pull_scope.py` | Pull labeled ad groups and build live inventory |
| 2 | `pull_search_terms.py` | Pull search terms per served ad group |
| 3 | `filter_by_cost.py` | Drop low-spend terms and protect conversion-value terms |
| 4 | `dedupe_cache.py` | Skip served ad-group/term pairs already cached |
| 5 | `classify_batch.py` | Agent 1: Haiku route classifier |
| 5b | `guards.py` | Deterministic corrections, fused-anchor keeps, source-brand normalization, and dual-anchor keep guards |
| 6 | `confidence_gate.py` / `escalate.py` | Escalate low-confidence/REVIEW/guarded rows to Sonnet |
| 7 | `scope_router.py` | Convert route to KEEP/NEGATE/NOOP per served ad group |
| 8 | `dry_run_report.py` | Write review CSV report |
| 9 | `upload_negatives.py` | Upload exact-match negatives when live |
| 10 | `update_cache.py` | Cache completed decisions |

`NEGATE_ALL` rows are routed to campaign-level negatives for the served campaign. Other
negative routes are ad-group-level exact-match negatives. Dual-anchor rows can carry
`force_keep_in`, which makes the router keep a term in the served ad group when the term
contains a valid target anchor for that ad group even if the classifier's single route points
elsewhere.

## Prompt And Config

The single source of truth is:

```text
verticals/dating_geo/prompts/classifier.md
```

Its first fenced YAML block under `ACCOUNT BLOCK` is parsed by `config.load_account_config()`.
Editing that block updates both the prompt and router behavior.

The live inventory is appended to the system prompt as:

```text
## Live ad-group inventory
<Ad group>\t<Campaign>
```

## Golden Eval

The committed golden set lives at:

```text
verticals/dating_geo/eval/golden_set.csv
```

Run the trust check before going live:

```bash
python3 eval_golden.py
```

The eval compares operational action accuracy first: whether the predicted route causes the
same `KEEP`/`NEGATE` action at the served ad group as the oracle route. Route exact-match is
reported as a stricter diagnostic. False-negates are printed loudly because they are the
dangerous error.

## Porting To A New Account

A new account needs:

- Google Ads auth/profile.
- A new `ACCOUNT BLOCK` in a copy of `classifier.md` with campaign generals, sub-regions,
  language map, tiebreakers, and special cases.
- A relabeled golden set produced by:

```bash
python3 relabel_golden.py \
  --old verticals/dating_geo/eval/golden_set.csv \
  --out verticals/dating_geo/eval/golden_set_<account>.csv \
  --live-inventory \
  --account-profile accounts/<account_key>.local.yaml
```

`relabel_golden.py` carries account-independent rows over verbatim, re-proposes only
geo-dependent rows under the new inventory, and marks changed answers with
`needs_review=CHANGED`. Then append roughly 50-80 of the new account's own highest-cost
terms for its brands/languages and run `eval_golden.py`.

Do not rebuild the old `targets.yaml` anchor layer. It is intentionally gone.

## Validation

```bash
python3 tools/validate_targets.py
python3 -m unittest discover -s tests
```

Do not commit `.env`, `google-ads.yaml`, `data/`, `logs/`, or generated `reports/`.

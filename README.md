# Google Ads Negatives Agent

Profile-driven Google Ads negative-keyword pipeline.

The script pulls search terms from labeled Google Ads ad groups, classifies each
term with deterministic anchors and Claude Haiku, writes a review report, and can
upload exact-match negative keywords at the ad-group level.

It is designed so new accounts or verticals can be added by swapping config,
target, policy, and prompt files instead of rewriting Python logic.

## Safety First

The pipeline defaults to dry-run.

Dry-run:

- pulls real Google Ads data
- can call the Anthropic API
- writes a CSV report
- does not upload negatives
- does not update the local classified-term cache unless `--write-cache` is passed

Live upload requires:

```bash
python3 run.py --no-dry-run --days 30
```

All automatic negatives are currently uploaded as:

- exact match
- ad-group level

Campaign-level upload paths exist in code, but current routing policy does not
populate campaign-level negatives automatically.

## Quick Start

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Validate target data and run tests:

```bash
python3 tools/validate_targets.py
python3 -m unittest discover -s tests
```

Run a dry run with a local account profile:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30
```

Run a single target/region:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30 --region ukraine
```

Re-evaluate everything regardless of local cache:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30 --ignore-cache
```

Persist dry-run classifications to local cache intentionally:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30 --write-cache
```

Run live after reviewing the report:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --no-dry-run --days 30
```

## Account Profile Template

The committed account profile is a placeholder template:

```text
accounts/dating_main.yaml
```

It uses placeholder account-specific values:

- customer ID: `<GOOGLE_ADS_CUSTOMER_ID>`
- vertical: `<VERTICAL_KEY>` such as `dating_geo`
- credentials path: `<GOOGLE_ADS_YAML_PATH>`
- master ad-group label: `<MASTER_AD_GROUP_LABEL>`
- region label prefix: `<REGION_LABEL_PREFIX>`

Real account profiles should be local-only and ignored by Git:

```text
accounts/<account_key>.local.yaml
```

Credentials and secrets are intentionally not committed:

```text
.env
google-ads.yaml
```

## Pipeline Stages

`run.py` orchestrates the full pipeline:

| Stage | File | Responsibility |
|---:|---|---|
| 1 | `pull_scope.py` | Find labeled ad groups and map them to target keys |
| 2 | `pull_search_terms.py` | Pull search terms and metrics from Google Ads |
| 3 | `filter_by_cost.py` | Split terms into active, protected, and below-threshold |
| 4 | `dedupe_cache.py` | Skip terms already classified in local cache |
| 5 | `regex_anchor_check.py` | Deterministic KEEP/NEGATE using own/sibling anchors |
| 6 | `llm_classify_batch.py` | Classify uncertain terms with Claude Haiku |
| 7 | `confidence_gate.py` | Convert LLM score into KEEP/NEGATE/DEFER |
| 8 | `scope_router.py` | Route negatives to ad-group level |
| 9 | `dry_run_report.py` | Write review CSV report |
| 10 | `upload_negatives.py` | Upload exact-match negatives when live |
| 11 | `update_cache.py` | Update local classified-term cache after live run |

## Repository Map

```text
.
├── run.py
├── config.py
├── target_loader.py
├── accounts/
│   └── dating_main.yaml
├── verticals/
│   └── dating_geo/
│       ├── policy.yaml
│       ├── targets.yaml
│       └── prompts/
│           ├── classifier.md
│           ├── region_context.md
│           ├── judgment_rules.md
│           └── archetypes.yaml
├── tools/
│   ├── validate_targets.py
│   └── remove_negatives.py
├── tests/
├── docs/
│   └── new_account_or_vertical.md
├── data/
├── logs/
├── reports/
├── requirements.txt
├── CLAUDE.md
└── README.md
```

## Swappable Parts

The main scaling idea is: Python is the engine; account and vertical behavior
come from files.

### Account Profile

Account-specific settings live in:

```text
accounts/<account_key>.yaml
```

Example:

```yaml
account_key: <ACCOUNT_KEY>
vertical_key: <VERTICAL_KEY>
customer_id: "<GOOGLE_ADS_CUSTOMER_ID>"
google_ads_yaml: <GOOGLE_ADS_YAML_PATH>

labels:
  master: <MASTER_AD_GROUP_LABEL>
  region_prefix: <REGION_LABEL_PREFIX>

paths:
  data_dir: data
  logs_dir: logs
  reports_dir: reports
  classified_terms: data/classified_terms.json
```

Swap this when adding a new Google Ads account.

Run with a non-default profile:

```bash
python3 run.py --account-profile accounts/<account_key>.local.yaml --dry-run --days 30
```

### Vertical Policy

Business thresholds and model settings live in:

```text
verticals/<vertical_key>/policy.yaml
```

Current examples:

```yaml
thresholds:
  cost: 3.0
  conversion_value_protection: 100.0
  score: 6

llm:
  model: claude-haiku-4-5-20251001
  batch_size: 50
  prompt_cache: true
```

Swap this when a vertical needs different spend thresholds, score thresholds,
upload caps, model, or prompt-cache settings.

### Target And Anchor Data

Target groups and anchor relationships live in:

```text
verticals/<vertical_key>/targets.yaml
```

Each target defines:

- ad group name
- archetype
- display label for LLM context
- own anchors
- sibling/wrong-group anchors

Example shape:

```yaml
ukraine:
  ad_group_name: Ukraine
  archetype: hero_country
  target_country: Ukraine
  target_region_label: Ukraine / Ukrainian
  own_anchors:
    - ukraine
    - ukrainian
  sibling_anchors:
    - poland
    - polish
    - russia
    - russian
```

Always validate after editing:

```bash
python3 tools/validate_targets.py
```

### LLM Prompts

Prompt files live in:

```text
verticals/<vertical_key>/prompts/
```

| File | Purpose |
|---|---|
| `classifier.md` | Cacheable vertical doctrine and edge-case rules |
| `region_context.md` | Per-target context template rendered for each batch |
| `archetypes.yaml` | Broad/hero/catch-all/hybrid ad group behavior |
| `judgment_rules.md` | Older judgment-rule source text kept for reference |

The current LLM request sends:

1. Cacheable system block:
   - `classifier.md`
   - `archetypes.yaml`

2. Uncached system block:
   - rendered `region_context.md`
   - current target label
   - current target archetype
   - own anchors
   - sibling anchors
   - score threshold

3. User message:
   - batch of search terms

Claude returns strict JSON:

```json
[
  {
    "term": "dating site",
    "score": 1,
    "anchor": null,
    "reason": "Generic dating query with no target signal."
  }
]
```

## Target Archetypes

Archetypes live in:

```text
verticals/dating_geo/prompts/archetypes.yaml
```

Current archetypes:

| Archetype | Meaning |
|---|---|
| `pan_regional_demonym` | Broad group like Asia or Latina |
| `hero_country` | Dedicated country group like Korea, Japan, Ukraine |
| `catch_all` | Smaller-country bucket inside a broader region |
| `hybrid` | Broad regional plus smaller-country catch-all |

This structure lets the same classifier distinguish cases like:

- `Asian dating` should KEEP in broad Asia.
- `Asian dating` should NEGATE in Korea.
- `Korean dating` should NEGATE in broad Asia.
- `Korean dating` should KEEP in Korea.

## Search-Term Filtering Logic

Search terms are pulled from Google Ads for scoped ad groups over the configured
date window.

Current filtering:

| Bucket | Condition | Outcome |
|---|---|---|
| Protected | `conversions_value >= CV threshold` | Never negate |
| Below threshold | `cost < cost threshold` | Drop from classification |
| Active | Cost above threshold and not protected | Regex/LLM evaluation |

Current thresholds are in:

```text
verticals/dating_geo/policy.yaml
```

## Local Classified-Term Cache

The local cache is:

```text
data/classified_terms.json
```

It prevents repeated classification of the same term for the same account,
vertical, and target.

New entries include:

- `account_key`
- `vertical_key`
- `policy_version`
- `prompt_version`
- `region_key`
- `term`
- `decision`
- `confidence`
- `source`
- `timestamp`

Dry-run does not write this cache unless `--write-cache` is passed.

For audits or prompt changes, use:

```bash
python3 run.py --dry-run --days 30 --ignore-cache
```

At larger scale, this JSON cache should move to SQLite.

## Anthropic Prompt Cache

Anthropic prompt caching is enabled in:

```text
verticals/dating_geo/policy.yaml
```

```yaml
llm:
  prompt_cache: true
```

Stage 6 prints token usage like:

```text
regular_input=109286, cache_write=0, cache_read=132440, output=14619
```

Meanings:

| Field | Meaning |
|---|---|
| `regular_input` | Non-cached input tokens |
| `cache_write` | Tokens written to Anthropic prompt cache |
| `cache_read` | Tokens read from Anthropic prompt cache |
| `output` | Claude output tokens |

Prompt cache is API-side and temporary. It is not stored in this repo.

## Reports

Reports are written to:

```text
reports/run_YYYY-MM-DD_HHMMSS.csv
```

Report rows include:

- account/vertical metadata
- term
- ad group
- campaign
- decision
- score
- source
- target scope
- cost/click/conversion metrics
- reason

Review these reports before live upload.

## Upload Behavior

Live uploads happen in:

```text
upload_negatives.py
```

Current behavior:

- exact-match keyword negatives
- ad-group level
- existing negatives fetched first to avoid duplicates
- partial failure enabled for mutate calls
- upload errors logged to `logs/upload_errors.jsonl`

The critical code path sets:

```python
criterion.negative = True
criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
```

## Validation And Tests

Run before important changes:

```bash
python3 tools/validate_targets.py
python3 -m unittest discover -s tests
```

Compile check:

```bash
python3 -X pycache_prefix=.pycache_check -m py_compile \
  config.py target_loader.py run.py dry_run_report.py pull_scope.py \
  regex_anchor_check.py llm_classify_batch.py confidence_gate.py \
  dedupe_cache.py update_cache.py tools/validate_targets.py
```

## Adding A New Account Or Vertical

Use:

```text
docs/new_account_or_vertical.md
```

Short version:

- New account: copy `accounts/dating_main.yaml`.
- New vertical: create `verticals/<vertical_key>/`.
- Swap:
  - `policy.yaml`
  - `targets.yaml`
  - `prompts/classifier.md`
  - `prompts/region_context.md`
  - `prompts/archetypes.yaml`

Then validate and dry-run before going live.

## Known Scaling Notes

This repo is now modular enough for more accounts/verticals, but there are
expected future improvements:

- Move `data/classified_terms.json` to SQLite before large multi-account scale.
- Add stronger prompt/policy versioning when classification behavior changes.
- Consider separate review workflows before live upload.
- Consider rate-limit handling if full cache-cleared runs become frequent.

## Git-Ignored Runtime Files

These are intentionally ignored:

```text
.env
google-ads.yaml
data/
logs/
reports/
__pycache__/
.pycache_check/
```

Do not commit credentials, OAuth tokens, local cache, logs, or generated reports.

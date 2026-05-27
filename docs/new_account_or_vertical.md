# New Account Or Vertical

## New Account

1. Create a local account profile with Google Ads auth, customer ID, output paths,
   and the master label used to include ad groups.
2. Copy `verticals/dating_geo/prompts/classifier.md` if the account needs its own
   doctrine/config.
3. Edit only the `ACCOUNT BLOCK`: `generals`, `sub_regions`, `language_map`,
   `tiebreakers`, `special_cases`, and account-specific brand routing such as
   `campaign_brands`.
4. Validate the prompt config:

   ```bash
   python3 tools/validate_targets.py
   ```

5. Relabel the golden set against the new live inventory:

   ```bash
   python3 relabel_golden.py \
     --old verticals/dating_geo/eval/golden_set.csv \
     --out verticals/dating_geo/eval/golden_set_<account>.csv \
     --live-inventory \
     --account-profile accounts/<account_key>.local.yaml
   ```

6. Review only `needs_review=CHANGED` rows, then append roughly 50-80 of that
   account's highest-cost search terms for account-specific brands/languages.
7. Run `eval_golden.py`, then run live traffic in `--shadow`, then dry-run, then live.

No `targets.yaml` rebuild is needed. The old anchor layer is intentionally gone.

## New Vertical

1. Add `verticals/<vertical_key>/policy.yaml`.
2. Add `verticals/<vertical_key>/prompts/classifier.md` with a vertical doctrine and
   an `ACCOUNT BLOCK`.
3. Add `verticals/<vertical_key>/eval/golden_set.csv`.
4. Add the vertical implementation modules expected by `vertical_loader.py`:
   `geo_anchor_map.py` with `build_anchor_index(...)`, and `geo_gate.py` with
   `detect_geo(...)`, `served_anchor_in_term(...)`, and `route_decision(...)`.
5. Point an account profile at the new vertical and prompt template.
6. Build/adjust eval categories until action accuracy and false-negates are acceptable.

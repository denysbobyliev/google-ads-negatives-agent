# New Account Or Vertical Checklist

Use this checklist when adapting the pipeline to a different Google Ads account
or business vertical.

## New Account, Same Vertical
1. Copy `accounts/dating_main.yaml` to `accounts/<account_key>.yaml`.
2. Set `account_key`, `customer_id`, `google_ads_yaml`, and output paths.
3. Confirm label names:
   - `labels.master`
   - `labels.region_prefix`
4. Confirm the Google Ads account has matching ad-group labels.
5. Run:
   ```bash
   python3 tools/validate_targets.py
   python3 run.py --account-profile accounts/<account_key>.yaml --dry-run --days 30
   ```
6. Review the generated report before using `--no-dry-run`.

## New Vertical
1. Create `verticals/<vertical_key>/`.
2. Add `policy.yaml` with thresholds, score cutoff, caps, defer rule, model, and token costs.
3. Add `targets.yaml` with target keys, ad group names, archetypes, own anchors, and sibling anchors.
4. Add `prompts/classifier.md` as the cacheable vertical doctrine.
5. Add `prompts/region_context.md` as the per-target context template.
6. Add `prompts/archetypes.yaml`.
6. Point an account profile at the new vertical files:
   ```yaml
   vertical_key: <vertical_key>
   policy_yaml: verticals/<vertical_key>/policy.yaml
   targets_yaml: verticals/<vertical_key>/targets.yaml
   prompt_template: verticals/<vertical_key>/prompts/classifier.md
   region_context_template: verticals/<vertical_key>/prompts/region_context.md
   archetypes_yaml: verticals/<vertical_key>/prompts/archetypes.yaml
   ```
7. Run:
   ```bash
   python3 tools/validate_targets.py
   python3 -m unittest discover -s tests
   python3 run.py --account-profile accounts/<account_key>.yaml --dry-run --days 30
   ```

## Do Not Hardcode
- Customer IDs in Python.
- Prompt text in Python.
- Thresholds or model names in stage modules.
- Credential paths outside account profiles.
- New target anchors in `regions.yaml`.

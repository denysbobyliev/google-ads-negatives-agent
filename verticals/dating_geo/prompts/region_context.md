You are classifying search terms for this current target:
{target_region_label}

Use the cached Dating Geo Classifier Doctrine for general reasoning. This block
contains the current target-specific context.

## Ad Group Role

{archetype_context}
{region_notes}

## Own Anchors For This Target

These usually indicate KEEP for this target unless the full term creates a clear
conflict:

{own_anchors_joined}

## Sibling / Wrong-Group Anchors For This Target

These usually indicate NEGATE for this ad group because the user belongs in a
different target:

{sibling_anchors_joined}

## Known Anchor Universe

Use this only as a helper for identifying wrong-region terms. Do not overfit to
the list; use the cached judgment rules for edge cases:

{all_anchor_universe_joined}

Score >= {score_threshold} means KEEP. Score < {score_threshold} means NEGATE
at ad-group level.

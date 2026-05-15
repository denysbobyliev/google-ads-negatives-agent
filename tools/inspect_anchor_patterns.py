from __future__ import annotations
"""Inspect compiled Stage 5 anchor patterns for one target region."""

import argparse
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
import target_loader


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")


def _substring_matches(term: str, anchors: list[dict]) -> list[str]:
    matches = []
    for token in _normalize(term).split():
        for anchor in anchors:
            anchor_text = anchor["anchor"]
            if token == anchor_text or token in anchor["excluded_tokens"]:
                continue
            if anchor_text in token:
                matches.append(f"{anchor_text} in {token}")
    return matches


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect compiled Stage 5 anchor patterns")
    parser.add_argument("--region", required=True, help="Region key from targets.yaml")
    parser.add_argument(
        "--test-term",
        action="append",
        default=[],
        help="Term to test against this region's compiled anchors",
    )
    args = parser.parse_args()

    policy = config.load_policy(config.POLICY_YAML)
    universe = target_loader.load_anchor_patterns(policy)
    if args.region not in universe:
        raise SystemExit(f"Unknown region: {args.region}")

    region = universe[args.region]
    print(f"Region: {args.region}")
    print("\nOwn standalone patterns:")
    for anchor, pattern in region["own"]:
        print(f"  {anchor}: {pattern.pattern}")
    print("\nSibling standalone patterns:")
    for anchor, pattern in region["sibling"]:
        print(f"  {anchor}: {pattern.pattern}")
    print("\nOwn substring anchors:")
    for anchor in region["own_substring"]:
        excluded = ", ".join(sorted(anchor["excluded_tokens"])) or "-"
        print(f"  {anchor['anchor']} (length {anchor['length']}, excluded: {excluded})")
    print("\nSibling substring anchors:")
    for anchor in region["sibling_substring"]:
        excluded = ", ".join(sorted(anchor["excluded_tokens"])) or "-"
        print(f"  {anchor['anchor']} (length {anchor['length']}, excluded: {excluded})")

    for term in args.test_term:
        term_norm = _normalize(term)
        own_standalone = [a for a, p in region["own"] if p.search(term_norm)]
        sibling_standalone = [a for a, p in region["sibling"] if p.search(term_norm)]
        print(f"\nTest term: {term}")
        print(f"  own standalone: {', '.join(own_standalone) or '-'}")
        print(f"  sibling standalone: {', '.join(sibling_standalone) or '-'}")
        print(f"  own substring: {', '.join(_substring_matches(term, region['own_substring'])) or '-'}")
        print(
            "  sibling substring: "
            f"{', '.join(_substring_matches(term, region['sibling_substring'])) or '-'}"
        )


if __name__ == "__main__":
    main()

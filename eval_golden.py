from __future__ import annotations
"""Compatibility wrapper for the active vertical's golden eval harness."""

import importlib

import config


main = importlib.import_module(f"verticals.{config.VERTICAL_KEY}.eval.eval_golden").main


if __name__ == "__main__":
    main()

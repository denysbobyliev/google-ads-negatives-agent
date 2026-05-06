from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/google-ads-agent/.env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
REGIONS_YAML = os.path.join(BASE_DIR, "regions.yaml")
CLASSIFIED_TERMS_PATH = os.path.join(DATA_DIR, "classified_terms.json")
GOOGLE_ADS_YAML = os.path.expanduser("~/google-ads-agent/google-ads.yaml")

CUSTOMER_ID = "<GOOGLE_ADS_CUSTOMER_ID>"

DRY_RUN = True
DAYS = 30

COST_THRESHOLD = 3.0
CV_PROTECTION_THRESHOLD = 100.0

MAX_AG_NEGATIVES_PER_RUN = 20
MAX_CAMPAIGN_NEGATIVES_PER_RUN = 50

# Score-3 terms are negated but deferred to the next run when an ad group
# already has enough clear negations (score 1-2). Set to None to disable.
DEFER_NEGATE_SCORE = 3

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Haiku: low-cost batch classification (negatives pipeline)
# Sonnet is used in the ads-generation project, not here
MODEL = "claude-haiku-4-5-20251001"
LLM_BATCH_SIZE = 50
LLM_COST_PER_1K_INPUT_TOKENS = 0.003
LLM_COST_PER_1K_OUTPUT_TOKENS = 0.015

from __future__ import annotations
import functools
import os
import re
from dotenv import load_dotenv
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

ACCOUNTS_DIR = os.path.join(BASE_DIR, "accounts")
DEFAULT_ACCOUNT_PROFILE = os.path.join(ACCOUNTS_DIR, "dating_main.yaml")
ACCOUNT_KEY = "example_account"
VERTICAL_KEY = "dating_geo"
POLICY_VERSION = "legacy"
PROMPT_VERSION = "legacy"
VERTICALS_DIR = os.path.join(BASE_DIR, "verticals")
VERTICAL_DIR = os.path.join(VERTICALS_DIR, VERTICAL_KEY)
POLICY_YAML = os.path.join(VERTICAL_DIR, "policy.yaml")
PROMPT_TEMPLATE_PATH = os.path.join(VERTICAL_DIR, "prompts", "classifier.md")

DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CLASSIFIED_TERMS_PATH = os.path.join(DATA_DIR, "classified_terms.json")
GOOGLE_ADS_YAML = os.path.join(BASE_DIR, "google-ads.yaml")

CUSTOMER_ID = ""
MASTER_LABEL = ""

DRY_RUN = True
DAYS = 30

COST_THRESHOLD = 3.0
CV_PROTECTION_THRESHOLD = 100.0
SCORE_THRESHOLD = 6

MAX_AG_NEGATIVES_PER_RUN = 20
MAX_CAMPAIGN_NEGATIVES_PER_RUN = 50

# Score-3 terms are negated but deferred to the next run when an ad group
# already has enough clear negations (score 1-2). Set to None to disable.
DEFER_NEGATE_SCORE = 3

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Haiku: low-cost batch classification (negatives pipeline)
# Sonnet is used in the ads-generation project, not here
MODEL = "claude-haiku-4-5-20251001"
HAIKU_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-6"
LLM_BATCH_SIZE = 50
LLM_USE_BATCH_API = True
LLM_BATCH_POLL_SECONDS = 10
LLM_BATCH_TIMEOUT_SECONDS = 1800
LLM_GATE_HIGH_CONFIDENCE = 0.80
LLM_ESCALATE_BELOW_CONFIDENCE = 0.80
LLM_COST_PER_1K_INPUT_TOKENS = 0.003
LLM_COST_PER_1K_OUTPUT_TOKENS = 0.015
LLM_PROMPT_CACHE_ENABLED = True
LLM_CACHE_WRITE_INPUT_MULTIPLIER = 1.25
LLM_CACHE_READ_INPUT_MULTIPLIER = 0.10
SEARCH_TERM_PULL_WORKERS = 4


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def load_account_profile(path: str = DEFAULT_ACCOUNT_PROFILE) -> dict:
    with open(path, encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}
    return profile


def load_policy(path: str = POLICY_YAML) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@functools.lru_cache(maxsize=8)
def load_account_config(path: str | None = None) -> dict:
    """Parse the ACCOUNT BLOCK embedded in the classifier prompt."""
    prompt_path = path or PROMPT_TEMPLATE_PATH
    with open(prompt_path, encoding="utf-8") as f:
        md = f.read()
    match = re.search(r"ACCOUNT BLOCK.*?```yaml\s*(.*?)```", md, re.S)
    if not match:
        raise ValueError(f"No ACCOUNT BLOCK yaml fence found in {prompt_path}")
    return yaml.safe_load(match.group(1)) or {}


def apply_policy(path: str | None = None) -> dict:
    """Apply vertical policy settings to legacy config globals."""
    global POLICY_YAML, COST_THRESHOLD, CV_PROTECTION_THRESHOLD, SCORE_THRESHOLD
    global MAX_AG_NEGATIVES_PER_RUN, MAX_CAMPAIGN_NEGATIVES_PER_RUN
    global DEFER_NEGATE_SCORE, MODEL, HAIKU_MODEL, SONNET_MODEL, LLM_BATCH_SIZE
    global LLM_USE_BATCH_API, LLM_BATCH_POLL_SECONDS, LLM_BATCH_TIMEOUT_SECONDS
    global LLM_GATE_HIGH_CONFIDENCE, LLM_ESCALATE_BELOW_CONFIDENCE
    global LLM_COST_PER_1K_INPUT_TOKENS, LLM_COST_PER_1K_OUTPUT_TOKENS
    global LLM_PROMPT_CACHE_ENABLED, SEARCH_TERM_PULL_WORKERS

    if path is not None:
        POLICY_YAML = _resolve_path(path)

    policy = load_policy(POLICY_YAML)
    thresholds = policy.get("thresholds", {})
    COST_THRESHOLD = float(thresholds.get("cost", COST_THRESHOLD))
    CV_PROTECTION_THRESHOLD = float(
        thresholds.get("conversion_value_protection", CV_PROTECTION_THRESHOLD)
    )
    SCORE_THRESHOLD = int(thresholds.get("score", SCORE_THRESHOLD))

    caps = policy.get("caps", {})
    MAX_AG_NEGATIVES_PER_RUN = int(caps.get("max_ad_group_negatives_per_run", MAX_AG_NEGATIVES_PER_RUN))
    MAX_CAMPAIGN_NEGATIVES_PER_RUN = int(
        caps.get("max_campaign_negatives_per_run", MAX_CAMPAIGN_NEGATIVES_PER_RUN)
    )

    defer = policy.get("defer", {})
    DEFER_NEGATE_SCORE = defer.get("negate_score", DEFER_NEGATE_SCORE)

    llm = policy.get("llm", {})
    MODEL = llm.get("model", MODEL)
    HAIKU_MODEL = llm.get("haiku_model", llm.get("model", HAIKU_MODEL))
    SONNET_MODEL = llm.get("sonnet_model", SONNET_MODEL)
    LLM_BATCH_SIZE = int(llm.get("batch_size", LLM_BATCH_SIZE))
    LLM_USE_BATCH_API = bool(llm.get("use_batch_api", LLM_USE_BATCH_API))
    LLM_BATCH_POLL_SECONDS = int(llm.get("batch_poll_seconds", LLM_BATCH_POLL_SECONDS))
    LLM_BATCH_TIMEOUT_SECONDS = int(
        llm.get("batch_timeout_seconds", LLM_BATCH_TIMEOUT_SECONDS)
    )
    LLM_GATE_HIGH_CONFIDENCE = float(
        llm.get("gate_high_confidence", LLM_GATE_HIGH_CONFIDENCE)
    )
    LLM_ESCALATE_BELOW_CONFIDENCE = float(
        llm.get("escalate_below_confidence", LLM_GATE_HIGH_CONFIDENCE)
    )
    LLM_PROMPT_CACHE_ENABLED = bool(llm.get("prompt_cache", LLM_PROMPT_CACHE_ENABLED))
    costs = llm.get("cost_per_1k_tokens", {})
    LLM_COST_PER_1K_INPUT_TOKENS = float(costs.get("input", LLM_COST_PER_1K_INPUT_TOKENS))
    LLM_COST_PER_1K_OUTPUT_TOKENS = float(costs.get("output", LLM_COST_PER_1K_OUTPUT_TOKENS))

    google_ads = policy.get("google_ads", {})
    SEARCH_TERM_PULL_WORKERS = max(
        1,
        int(google_ads.get("search_term_pull_workers", SEARCH_TERM_PULL_WORKERS)),
    )

    return policy


def apply_account_profile(path: str = DEFAULT_ACCOUNT_PROFILE) -> dict:
    """Apply account-level settings from YAML to the legacy config module.

    The rest of the pipeline still imports config globals. Keeping this bridge
    small lets us migrate stage modules incrementally without breaking scripts.
    """
    global ACCOUNT_KEY, VERTICAL_KEY, POLICY_VERSION, PROMPT_VERSION
    global VERTICAL_DIR, POLICY_YAML, PROMPT_TEMPLATE_PATH
    global CUSTOMER_ID, GOOGLE_ADS_YAML
    global DATA_DIR, LOGS_DIR, REPORTS_DIR, CLASSIFIED_TERMS_PATH
    global MASTER_LABEL

    profile = load_account_profile(path)
    ACCOUNT_KEY = profile.get("account_key", ACCOUNT_KEY)
    VERTICAL_KEY = profile.get("vertical_key", VERTICAL_KEY)
    POLICY_VERSION = profile.get("policy_version", POLICY_VERSION)
    PROMPT_VERSION = profile.get("prompt_version", PROMPT_VERSION)
    VERTICAL_DIR = os.path.join(VERTICALS_DIR, VERTICAL_KEY)
    POLICY_YAML = os.path.join(VERTICAL_DIR, "policy.yaml")
    PROMPT_TEMPLATE_PATH = os.path.join(VERTICAL_DIR, "prompts", "classifier.md")
    CUSTOMER_ID = str(profile.get("customer_id", CUSTOMER_ID)).replace("-", "")

    if profile.get("google_ads_yaml"):
        GOOGLE_ADS_YAML = _resolve_path(profile["google_ads_yaml"])

    labels = profile.get("labels", {})
    MASTER_LABEL = labels.get("master", MASTER_LABEL)

    paths = profile.get("paths", {})
    if paths.get("data_dir"):
        DATA_DIR = _resolve_path(paths["data_dir"])
    if paths.get("logs_dir"):
        LOGS_DIR = _resolve_path(paths["logs_dir"])
    if paths.get("reports_dir"):
        REPORTS_DIR = _resolve_path(paths["reports_dir"])
    CLASSIFIED_TERMS_PATH = paths.get(
        "classified_terms",
        os.path.join(DATA_DIR, "classified_terms.json"),
    )
    CLASSIFIED_TERMS_PATH = _resolve_path(CLASSIFIED_TERMS_PATH)

    if profile.get("policy_yaml"):
        POLICY_YAML = _resolve_path(profile["policy_yaml"])
    if profile.get("prompt_template"):
        PROMPT_TEMPLATE_PATH = _resolve_path(profile["prompt_template"])
    load_account_config.cache_clear()
    apply_policy(POLICY_YAML)

    return profile


apply_account_profile()

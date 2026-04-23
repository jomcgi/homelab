# Tests for no-hardcoded-max-tokens rule.
# Flags ModelSettings(max_tokens=<integer>) with literal token limits.
import os

from pydantic_ai import ModelSettings


def bad_hardcoded_max_tokens():
    # ruleid: no-hardcoded-max-tokens
    return ModelSettings(max_tokens=4096)


def bad_hardcoded_max_tokens_with_other_params():
    # ruleid: no-hardcoded-max-tokens
    return ModelSettings(temperature=0.7, max_tokens=8192)


def bad_hardcoded_max_tokens_trailing():
    # ruleid: no-hardcoded-max-tokens
    return ModelSettings(max_tokens=2048, temperature=0.5)


def ok_max_tokens_from_env():
    # ok: reading from environment variable is configurable
    return ModelSettings(max_tokens=int(os.environ.get("MAX_TOKENS", "4096")))


def ok_max_tokens_variable():
    # ok: using a variable is fine — caller controls the value
    limit = get_token_limit()
    return ModelSettings(max_tokens=limit)


def ok_no_max_tokens():
    # ok: no max_tokens set — model default applies
    return ModelSettings(temperature=0.7)


def ok_max_tokens_none():
    # ok: explicit None means no limit — intentional
    return ModelSettings(max_tokens=None)


def get_token_limit() -> int:
    return int(os.environ.get("MAX_TOKENS", "4096"))

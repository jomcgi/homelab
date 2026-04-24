# Tests for no-hardcoded-max-tokens-dict rule.
# Flags {"max_tokens": <integer>} in raw Python dict literals.
import os


def bad_hardcoded_max_tokens_dict():
    # ruleid: no-hardcoded-max-tokens-dict
    payload = {"max_tokens": 256}
    return payload


def bad_hardcoded_max_tokens_with_messages():
    # ruleid: no-hardcoded-max-tokens-dict
    payload = {"max_tokens": 4096, "messages": []}
    return payload


def bad_hardcoded_max_tokens_inline():
    # ruleid: no-hardcoded-max-tokens-dict
    return call_api({"model": "gpt-4", "max_tokens": 8192, "temperature": 0.7})


def ok_max_tokens_from_env():
    # ok: reading from environment variable is configurable
    payload = {"max_tokens": int(os.environ.get("MAX_TOKENS", "4096"))}
    return payload


def ok_max_tokens_variable():
    # ok: using a variable is fine — caller controls the value
    limit = get_token_limit()
    payload = {"max_tokens": limit}
    return payload


def ok_no_max_tokens():
    # ok: no max_tokens key in dict
    payload = {"model": "gpt-4", "messages": []}
    return payload


def ok_max_tokens_string_value():
    # ok: string value, not an integer literal
    payload = {"max_tokens": "4096"}
    return payload


def get_token_limit() -> int:
    return int(os.environ.get("MAX_TOKENS", "4096"))


def call_api(payload):
    pass

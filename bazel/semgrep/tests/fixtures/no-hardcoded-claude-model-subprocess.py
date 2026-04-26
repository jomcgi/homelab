# Tests for no-hardcoded-claude-model-subprocess rule.
# Flags create_subprocess_exec calls where '--model' is followed by a string literal.
import asyncio
import os


# ruleid: no-hardcoded-claude-model-subprocess
async def bad_hardcoded_model_exec():
    await asyncio.create_subprocess_exec(
        "claude",
        "--model",
        "claude-opus-4-5",
    )


# ruleid: no-hardcoded-claude-model-subprocess
async def bad_hardcoded_model_exec_multiarg():
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "--no-color",
        "--model",
        "claude-sonnet-4-5",
        "--max-turns",
        "10",
    )
    return proc


# ok: model name is read from an environment variable
async def ok_model_from_env():
    model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")
    await asyncio.create_subprocess_exec(
        "claude",
        "--model",
        model,
    )


# ok: model name comes from a variable (computed elsewhere)
async def ok_model_variable():
    model = get_model_name()
    await asyncio.create_subprocess_exec(
        "claude",
        "--model",
        model,
    )


# ok: no --model flag at all
async def ok_no_model_flag():
    await asyncio.create_subprocess_exec(
        "claude",
        "--no-color",
        "--max-turns",
        "5",
    )


def get_model_name() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")

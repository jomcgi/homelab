"""Qwen-driven research agent (Pydantic AI on llama.cpp).

Mirrors chat/agent.py shape but with a research-focused system prompt,
three retrieval tools, and a structured ResearchNote output type.
Sources are reconstructed mechanically from the agent's tool-call audit
trail (see derive_sources_bundle) -- Qwen's prose is never trusted to
faithfully list its own citations.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel import Session

from knowledge.research_tools import (
    search_knowledge as _search_knowledge_impl,
    web_fetch as _web_fetch_impl,
    web_search as _web_search_impl,
)

# Empty default deliberate: hardcoding the in-cluster URL is blocked by
# the no-hardcoded-k8s-service-url semgrep rule (release-name renames silently
# break DNS). The Helm chart injects LLAMA_CPP_URL via env from values.yaml;
# tests bypass this entirely by passing an explicit ``model=`` to
# ``create_research_agent``.
LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")
QWEN_MODEL_ID = "qwen3.6-27b"
PIPELINE_VERSION = "research-pipeline@v1"


_RESEARCH_SYSTEM_PROMPT = """\
You are a research agent for a knowledge graph. Your job is to research a
single term -- referenced in the user's vault but not yet defined -- and
produce a structured ResearchNote.

You have three tools:

- **search_knowledge(query)** -- query the user's existing vault notes.
  Use this FIRST. The user's prior thinking is more trusted than any web
  source.
- **web_search(query)** -- search the open web (SearXNG). Returns titles,
  snippets, and URLs.
- **web_fetch(url)** -- fetch a single URL's body. Use this to get the
  actual page content for the URLs that look most relevant from
  web_search results. Snippets alone are not enough to substantiate
  claims.

## Output

Return a ResearchNote with:
- ``summary`` (3-5 sentences): what the term means and why it matters.
- ``claims`` (list of Claim): each claim is one factual statement
  attributable to the evidence you retrieved. Only make a claim if you
  retrieved evidence supporting it. Quality over quantity -- 3 strong
  claims is better than 8 weak ones.

Do NOT invent citations. The harness records every tool call you make
and reconstructs the sources bundle automatically -- your job is just to
produce supportable claims.
"""


class Claim(BaseModel):
    text: str = Field(description="A single factual claim about the term.")


class ResearchNote(BaseModel):
    summary: str
    claims: list[Claim] = Field(default_factory=list)


@dataclass
class ResearchDeps:
    session: Session
    vault_root: Path


@dataclass(frozen=True)
class SourceEntry:
    tool: str  # "web_fetch" | "web_search" | "search_knowledge"
    url: str | None = None
    content_hash: str | None = None
    fetched_at: str | None = None
    query: str | None = None
    note_ids: list[str] = field(default_factory=list)
    result_urls: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def create_research_agent(
    *, model: Any | None = None, base_url: str | None = None
) -> Agent[ResearchDeps, ResearchNote]:
    """Build the Pydantic AI agent.

    Pass an explicit ``model`` (e.g. ``pydantic_ai.models.function.FunctionModel``)
    to drive a deterministic test loop; otherwise the default Qwen-on-llama.cpp
    model is used.
    """
    if model is None:
        url = base_url or LLAMA_CPP_URL
        model = OpenAIChatModel(
            QWEN_MODEL_ID,
            provider=OpenAIProvider(base_url=f"{url}/v1", api_key="not-needed"),
        )

    agent: Agent[ResearchDeps, ResearchNote] = Agent(
        model,
        deps_type=ResearchDeps,
        output_type=ResearchNote,
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        model_settings=ModelSettings(
            temperature=0.4,  # lower than chat -- research is less creative
            top_p=0.95,
        ),
    )

    @agent.tool
    async def search_knowledge(
        ctx: RunContext[ResearchDeps], query: str, limit: int = 5
    ) -> dict[str, Any]:
        """Query the user's vault for notes matching ``query``. Use first.

        Returns a structured dict so the harness can recover ``note_ids`` from
        the audit trail. The model still synthesises against ``text``; the
        rest is metadata for the citations bundle.
        """
        result = await _search_knowledge_impl(
            session=ctx.deps.session, query=query, limit=limit
        )
        return {"text": result.text, "note_ids": list(result.note_ids)}

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the open web. Returns titles + snippets + URLs.

        Plain string return is intentional: the URLs are extracted by regex
        downstream (``_URL_RE``) -- no structured shape is needed.
        """
        return await _web_search_impl(query)

    @agent.tool_plain
    async def web_fetch(url: str) -> dict[str, Any]:
        """Fetch a single URL's body. Use after web_search picks a candidate.

        Returns a dict carrying both the synth text (``text``) and the
        citation metadata (``url``/``content_hash``/``fetched_at``/etc.)
        that the harness needs to build a sources bundle.
        """
        result = await _web_fetch_impl(url)
        if result.skipped_reason:
            return {
                "url": url,
                "content_hash": None,
                "fetched_at": result.fetched_at,
                "skipped_reason": result.skipped_reason,
                "text": f"(skipped {url}: {result.skipped_reason})",
            }
        truncated_note = " (truncated)" if result.truncated else ""
        return {
            "url": result.url,
            "content_hash": result.content_hash,
            "fetched_at": result.fetched_at,
            "truncated": result.truncated,
            "skipped_reason": None,
            "text": f"URL: {result.url}{truncated_note}\n\n{result.body}",
        }

    return agent


_URL_RE = re.compile(r"URL:\s*(https?://\S+)")


def derive_sources_bundle(message_history: list[Any]) -> list[SourceEntry]:
    """Reconstruct the sources bundle from the agent's tool-call audit trail.

    Pydantic AI returns the run history as a ``list[ModelMessage]`` (each a
    ``ModelRequest`` or ``ModelResponse`` whose ``.parts`` carry the actual
    tool-call/tool-return parts). This function flattens that shape, then
    pairs each ``ToolCallPart`` with its matching ``ToolReturnPart`` *by
    ``tool_call_id``* (the only safe key when the same tool is invoked
    multiple times in a single run).

    Tolerates a flat list of bare parts as input as well, which keeps unit
    tests ergonomic.

    Tool-return content shapes (see the wrappers in ``create_research_agent``):
    - web_fetch -> dict with url/content_hash/fetched_at/skipped_reason/text
    - search_knowledge -> dict with text/note_ids
    - web_search -> str (URLs extracted via ``_URL_RE``)

    The harness is the source of truth for citations -- Qwen's prose
    output is never inspected for source attribution.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
    )

    parts: list[Any] = []
    for item in message_history:
        if isinstance(item, (ModelRequest, ModelResponse)):
            parts.extend(item.parts)
        else:
            # Tolerate a flat list of bare parts (test ergonomics).
            parts.append(item)

    sources: list[SourceEntry] = []
    pending: dict[str, ToolCallPart] = {}
    for part in parts:
        if isinstance(part, ToolCallPart):
            pending[part.tool_call_id] = part
        elif isinstance(part, ToolReturnPart):
            call = pending.pop(part.tool_call_id, None)
            if call is None:
                continue
            sources.append(_extract_source_entry(call, part))
    return sources


def _call_args_as_dict(call: Any) -> dict[str, Any]:
    """Best-effort dict view of a ToolCallPart's args.

    Production message shapes carry args as a JSON string (the OpenAI
    provider populates it from ``dtc.function.arguments``). Pydantic AI's
    ``BaseToolCallPart.args_as_dict`` already handles both shapes -- prefer
    it when available, fall back to a manual check otherwise.
    """
    fn = getattr(call, "args_as_dict", None)
    if callable(fn):
        try:
            return fn() or {}
        except Exception:
            logger.debug("args_as_dict() failed on tool call, returning empty dict")
            return {}
    args = getattr(call, "args", None)
    return args if isinstance(args, dict) else {}


def _extract_source_entry(call: Any, ret: Any) -> SourceEntry:
    name = call.tool_name
    args = _call_args_as_dict(call)
    content = getattr(ret, "content", None)

    if name == "web_fetch":
        url = args.get("url", "")
        if isinstance(content, dict):
            return SourceEntry(
                tool="web_fetch",
                url=content.get("url") or url,
                content_hash=content.get("content_hash"),
                fetched_at=content.get("fetched_at"),
                skipped_reason=content.get("skipped_reason"),
            )
        return SourceEntry(tool="web_fetch", url=url)

    if name == "search_knowledge":
        if isinstance(content, dict):
            return SourceEntry(
                tool="search_knowledge",
                query=args.get("query"),
                note_ids=list(content.get("note_ids", [])),
            )
        return SourceEntry(tool="search_knowledge", query=args.get("query"))

    if name == "web_search":
        urls: list[str] = []
        if isinstance(content, str):
            urls = _URL_RE.findall(content)
        return SourceEntry(tool="web_search", query=args.get("query"), result_urls=urls)

    return SourceEntry(tool=name)

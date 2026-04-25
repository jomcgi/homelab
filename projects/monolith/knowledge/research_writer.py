"""Vault writers for research raws and failed-research quarantine files.

Both writers produce idempotent, byte-stable markdown with YAML frontmatter
suitable for raw_ingest pickup. The schema of the frontmatter is the
ground-truth provenance for every atom that gets committed downstream.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from knowledge.research_agent import PIPELINE_VERSION, ResearchNote, SourceEntry
from knowledge.research_validator import (
    VALIDATOR_VERSION,
    ValidatedClaim,
    ValidatedResearch,
)

INBOX_RESEARCH_DIR = "_inbox/research"
FAILED_RESEARCH_DIR = "_failed_research"


def _source_to_fm(s: SourceEntry) -> dict[str, Any]:
    """Serialize a SourceEntry to a frontmatter-friendly dict, omitting Nones."""
    return {k: v for k, v in asdict(s).items() if v not in (None, [], "")}


def _yaml_dump(fm: dict) -> str:
    return yaml.dump(fm, default_flow_style=False, sort_keys=False)


def write_research_raw(
    *,
    vault_root: Path,
    slug: str,
    title: str,
    summary: str,
    supported_claims: list[ValidatedClaim],
    sources: list[SourceEntry],
    claims_dropped: int,
    qwen_model: str,
    sonnet_model: str,
    researched_at: str,
) -> Path:
    """Write the validated research raw to ``_inbox/research/<slug>.md``."""
    out_dir = vault_root / INBOX_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    fm = {
        "type": "research",
        "id": slug,
        "title": f"Research note: {title}",
        "derived_from_gap": slug,
        "qwen_model": qwen_model,
        "sonnet_model": sonnet_model,
        "validator_version": VALIDATOR_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sources": [_source_to_fm(s) for s in sources],
        "claims_supported": len(supported_claims),
        "claims_dropped": claims_dropped,
    }

    body_lines = [
        f"## Summary\n\n{summary}\n",
        "## Supported claims",
    ]
    for c in supported_claims:
        body_lines.append(f"- {c.text} _[{c.reason}]_")
    body_lines.append("")
    body_lines.append("## Sources")
    for s in sources:
        if s.tool == "web_fetch" and s.url:
            body_lines.append(f"- web_fetch: {s.url}")
        elif s.tool == "search_knowledge":
            body_lines.append(f"- search_knowledge: {s.query} → {s.note_ids}")
        elif s.tool == "web_search":
            body_lines.append(f"- web_search: {s.query} → {s.result_urls}")

    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path


def quarantine(
    *,
    vault_root: Path,
    slug: str,
    attempt: int,
    draft_note: ResearchNote,
    validated: ValidatedResearch,
    sources: list[SourceEntry],
    qwen_model: str,
    sonnet_model: str,
    researched_at: str,
) -> Path:
    """Write a fully-rejected research draft to ``_failed_research/<slug>-<N>.md``."""
    out_dir = vault_root / FAILED_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}-{attempt}.md"

    fm = {
        "type": "failed_research",
        "id": f"{slug}-{attempt}",
        "derived_from_gap": slug,
        "attempt": attempt,
        "qwen_model": qwen_model,
        "sonnet_model": sonnet_model,
        "validator_version": VALIDATOR_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sonnet_reasons": [
            {"claim": c.text, "verdict": c.verdict, "reason": c.reason}
            for c in validated.claims
        ],
        "parse_error": validated.parse_error,
        "timed_out": validated.timed_out,
        "sources_attempted": [_source_to_fm(s) for s in sources],
    }

    body_lines = [
        f"# Failed research draft (attempt {attempt})",
        "",
        "## Summary",
        "",
        draft_note.summary,
        "",
        "## Claims (Qwen)",
    ]
    for c in draft_note.claims:
        body_lines.append(f"- {c.text}")
    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path

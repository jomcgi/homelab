"""Markdown-aware text chunking for embedding."""

from __future__ import annotations

import re

from knowledge_graph.app.models import ChunkPayload


def _estimate_tokens(text: str) -> int:
    """Approximate token count. ~1.3 tokens per word is reasonable for English."""
    return int(len(text.split()) * 1.3)


def _split_by_headers(content: str) -> list[tuple[str, str]]:
    """Split markdown into (header, body) pairs by h1-h3 headers."""
    pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    sections: list[tuple[str, str]] = []
    last_pos = 0
    last_header = ""

    for match in pattern.finditer(content):
        if last_pos < match.start():
            body = content[last_pos : match.start()].strip()
            if body:
                sections.append((last_header, body))
        last_header = match.group(0).strip()
        last_pos = match.end()

    # Remaining content after last header
    remaining = content[last_pos:].strip()
    if remaining:
        sections.append((last_header, remaining))

    # If no headers found, return entire content
    if not sections:
        sections = [("", content.strip())]

    return sections


def _split_paragraphs(text: str, max_tokens: int) -> list[str]:
    """Split text into paragraph-bounded chunks under max_tokens.

    Code blocks are kept intact even if they exceed the limit.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    # Split into paragraphs, preserving code blocks
    parts: list[str] = []
    in_code_block = False
    code_block_lines: list[str] = []

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code_block:
                code_block_lines.append(line)
                parts.append("\n".join(code_block_lines))
                code_block_lines = []
                in_code_block = False
            else:
                in_code_block = True
                code_block_lines = [line]
        elif in_code_block:
            code_block_lines.append(line)
        else:
            parts.append(line)

    # Handle unclosed code block
    if code_block_lines:
        parts.append("\n".join(code_block_lines))

    # Group lines into paragraphs (split on blank lines)
    paragraphs: list[str] = []
    current_para: list[str] = []
    for part in parts:
        if part.strip().startswith("```"):
            # Code block is its own paragraph
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []
            paragraphs.append(part)
        elif part.strip() == "":
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []
        else:
            current_para.append(part)
    if current_para:
        paragraphs.append("\n".join(current_para))

    # Build chunks from paragraphs
    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current_tokens + para_tokens > max_tokens and current:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0
        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_markdown(
    content: str,
    content_hash: str,
    source_url: str,
    source_type: str,
    title: str,
    author: str | None = None,
    published_at: str | None = None,
    max_tokens: int = 512,
    min_tokens: int = 50,
) -> list[ChunkPayload]:
    """Split markdown into chunks for embedding.

    Strategy:
    1. Split on markdown headers (h1-h3)
    2. Within sections, split on paragraph boundaries to stay under max_tokens
    3. Code blocks kept intact
    4. Small chunks merged with previous
    """
    sections = _split_by_headers(content)
    raw_chunks: list[tuple[str, str]] = []  # (header, chunk_text)

    for header, body in sections:
        sub_chunks = _split_paragraphs(body, max_tokens)
        for chunk in sub_chunks:
            raw_chunks.append((header, chunk))

    # Merge small chunks with previous
    merged: list[tuple[str, str]] = []
    for header, chunk_text in raw_chunks:
        if (
            merged
            and _estimate_tokens(chunk_text) < min_tokens
            and _estimate_tokens(merged[-1][1] + "\n\n" + chunk_text) <= max_tokens
        ):
            prev_header, prev_text = merged[-1]
            merged[-1] = (prev_header, prev_text + "\n\n" + chunk_text)
        else:
            merged.append((header, chunk_text))

    # Build ChunkPayload list
    payloads: list[ChunkPayload] = []
    for idx, (header, chunk_text) in enumerate(merged):
        payloads.append(
            ChunkPayload(
                content_hash=content_hash,
                chunk_index=idx,
                chunk_text=chunk_text,
                section_header=header,
                source_url=source_url,
                source_type=source_type,
                title=title,
                author=author,
                published_at=published_at,
            )
        )

    return payloads

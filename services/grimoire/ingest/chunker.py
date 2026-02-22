"""Content-aware chunking for D&D sourcebook PDFs.

Detects stat blocks, spells, items, and lore sections by pattern matching,
then falls back to overlapping-window chunking for general rules text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Minimum chunk size in characters. Chunks shorter than this are discarded.
MIN_CHUNK_CHARS = 20

# Token window settings for rules chunking.
WINDOW_TOKENS = 512
OVERLAP_TOKENS = 64


@dataclass
class Chunk:
    """A single chunk of sourcebook text with classification metadata."""

    text: str
    content_type: str  # stat_block, spell, rule, item, lore
    page: int = 0
    section: str = ""

    def is_valid(self) -> bool:
        """Return True if this chunk meets the minimum size requirement."""
        return len(self.text.strip()) >= MIN_CHUNK_CHARS


# ---------------------------------------------------------------------------
# Pattern indicators
# ---------------------------------------------------------------------------

# Stat block indicators -- need >= 2 to classify as stat_block.
_STAT_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bArmor\s+Class\b", re.IGNORECASE),
    re.compile(r"\bHit\s+Points\b", re.IGNORECASE),
    re.compile(r"\bChallenge\b", re.IGNORECASE),
    re.compile(r"\bSpeed\b.*\bft\b", re.IGNORECASE),
    re.compile(r"\bSTR\b.*\bDEX\b.*\bCON\b", re.IGNORECASE),
    re.compile(r"\bSaving\s+Throws?\b", re.IGNORECASE),
    re.compile(r"\bActions?\b\s*$", re.MULTILINE | re.IGNORECASE),
]

# Spell indicators -- need >= 3 to classify as spell.
_SPELL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bCasting\s+Time\b", re.IGNORECASE),
    re.compile(r"\bRange\b", re.IGNORECASE),
    re.compile(r"\bComponents?\b", re.IGNORECASE),
    re.compile(r"\bDuration\b", re.IGNORECASE),
    re.compile(r"\b(?:cantrip|1st|2nd|3rd|[4-9]th)[\s-]+level\b", re.IGNORECASE),
]

# Item indicators -- need >= 2 to classify as item.
_ITEM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bWondrous\s+Item\b", re.IGNORECASE),
    re.compile(r"\bRequires\s+Attunement\b", re.IGNORECASE),
    re.compile(r"\b(?:Weapon|Armor|Shield|Potion|Ring|Rod|Staff|Wand)\b.*\b(?:rare|uncommon|common|very rare|legendary|artifact)\b", re.IGNORECASE),
    re.compile(r"\brarity\b", re.IGNORECASE),
]

# Lore indicators -- need >= 2 to classify as lore.
_LORE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:history|legend|myth|tale|story|origin|ancient)\b", re.IGNORECASE),
    re.compile(r"\b(?:realm|kingdom|empire|deity|god|goddess|pantheon)\b", re.IGNORECASE),
    re.compile(r"\b(?:forgotten realms|greyhawk|eberron|dragonlance)\b", re.IGNORECASE),
]


def _count_matches(text: str, patterns: list[re.Pattern[str]]) -> int:
    """Count how many distinct patterns match anywhere in *text*."""
    return sum(1 for p in patterns if p.search(text))


def classify_content(text: str) -> str:
    """Classify a block of text into a content type.

    Priority order: stat_block > spell > item > lore > rule.
    """
    stat_hits = _count_matches(text, _STAT_BLOCK_PATTERNS)
    if stat_hits >= 2:
        return "stat_block"

    spell_hits = _count_matches(text, _SPELL_PATTERNS)
    if spell_hits >= 3:
        return "spell"

    item_hits = _count_matches(text, _ITEM_PATTERNS)
    if item_hits >= 2:
        return "item"

    lore_hits = _count_matches(text, _LORE_PATTERNS)
    if lore_hits >= 2:
        return "lore"

    return "rule"


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

# Markdown headers produced by pymupdf4llm.
_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _split_sections(md_text: str) -> list[tuple[str, str]]:
    """Split markdown into (section_title, body) pairs on h1-h3 headers."""
    sections: list[tuple[str, str]] = []
    last_pos = 0
    last_title = ""

    for m in _HEADER_RE.finditer(md_text):
        if last_pos < m.start():
            body = md_text[last_pos:m.start()].strip()
            if body:
                sections.append((last_title, body))
        last_title = m.group(2).strip()
        last_pos = m.end()

    # Trailing content after last header.
    tail = md_text[last_pos:].strip()
    if tail:
        sections.append((last_title, tail))

    if not sections:
        sections = [("", md_text.strip())]

    return sections


# ---------------------------------------------------------------------------
# Discrete-entity extraction (stat blocks, spells)
# ---------------------------------------------------------------------------

# A blank-line (or double-newline) boundary that we use to split paragraphs.
_PARA_SPLIT = re.compile(r"\n\s*\n")


def _extract_discrete_entities(
    paragraphs: list[str],
    detect_fn,
    min_indicators: int,
) -> tuple[list[str], list[str]]:
    """Pull out contiguous paragraph runs that match *detect_fn*.

    Returns (entities, remaining) where *entities* are the extracted blocks
    and *remaining* is everything else (order preserved).
    """
    entities: list[str] = []
    remaining: list[str] = []
    current_entity: list[str] = []

    for para in paragraphs:
        hits = detect_fn(para)
        if hits >= min_indicators or (current_entity and hits >= 1):
            current_entity.append(para)
        else:
            if current_entity:
                entities.append("\n\n".join(current_entity))
                current_entity = []
            remaining.append(para)

    if current_entity:
        entities.append("\n\n".join(current_entity))

    return entities, remaining


# ---------------------------------------------------------------------------
# Overlapping-window chunker for rules text
# ---------------------------------------------------------------------------

def _window_chunk(text: str, window: int = WINDOW_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Split *text* into overlapping windows of approximately *window* tokens.

    Each window overlaps with the previous by *overlap* tokens.
    """
    words = text.split()
    if not words:
        return []

    # Convert token counts to approximate word counts (tokens / 1.3).
    window_words = max(1, int(window / 1.3))
    overlap_words = max(0, int(overlap / 1.3))
    step = max(1, window_words - overlap_words)

    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + window_words]
        chunk = " ".join(chunk_words)
        if chunk.strip():
            chunks.append(chunk)
        i += step

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_page(md_text: str, page_number: int) -> list[Chunk]:
    """Chunk a single page of markdown-extracted PDF text.

    Strategy:
    1. Split into sections by markdown headers.
    2. Within each section, split into paragraphs.
    3. Extract discrete stat-block and spell entities.
    4. Remaining text is chunked with overlapping windows and classified.
    """
    sections = _split_sections(md_text)
    chunks: list[Chunk] = []

    for section_title, body in sections:
        paragraphs = [p.strip() for p in _PARA_SPLIT.split(body) if p.strip()]

        # 1. Extract stat blocks (discrete chunks).
        stat_blocks, paragraphs = _extract_discrete_entities(
            paragraphs,
            lambda t: _count_matches(t, _STAT_BLOCK_PATTERNS),
            min_indicators=2,
        )
        for sb in stat_blocks:
            c = Chunk(text=sb, content_type="stat_block", page=page_number, section=section_title)
            if c.is_valid():
                chunks.append(c)

        # 2. Extract spells (discrete chunks).
        spells, paragraphs = _extract_discrete_entities(
            paragraphs,
            lambda t: _count_matches(t, _SPELL_PATTERNS),
            min_indicators=3,
        )
        for sp in spells:
            c = Chunk(text=sp, content_type="spell", page=page_number, section=section_title)
            if c.is_valid():
                chunks.append(c)

        # 3. Remaining text: reassemble, classify, and window-chunk.
        remaining_text = "\n\n".join(paragraphs)
        if len(remaining_text.strip()) < MIN_CHUNK_CHARS:
            continue

        content_type = classify_content(remaining_text)
        windows = _window_chunk(remaining_text)
        for w in windows:
            c = Chunk(text=w, content_type=content_type, page=page_number, section=section_title)
            if c.is_valid():
                chunks.append(c)

    return chunks


def chunk_document(pages: list[tuple[int, str]]) -> list[Chunk]:
    """Chunk an entire document given as a list of (page_number, markdown_text) pairs."""
    all_chunks: list[Chunk] = []
    for page_number, md_text in pages:
        all_chunks.extend(chunk_page(md_text, page_number))
    return all_chunks

"""Rewrite [[wikilinks]] in source-note bodies to bare text.

When a stub note is reclassified as ``triaged: discardable`` (a "non-knowledge"
gap such as a one-off question, ephemeral todo, or a topic we deliberately
decline to capture), we delete the stub note. But the source notes that linked
to it still carry ``[[Stub Title]]`` wikilinks that would be re-detected by the
gap pipeline on the next gardener pass, recreating the same stub and undoing
the triage. This module closes that loop by rewriting those wikilinks back to
plain text in the source bodies, so the next gap-detection sweep sees prose
instead of an unresolved link.

The rewrite is intentionally narrow: only links whose slug appears in
``target_slugs`` are touched, and code regions (fenced and inline) are left
alone so that documentation-style examples like ``\\`[[example]]\\`` survive.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# Mirror knowledge.links so wikilink detection is identical in both directions.
_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_WIKILINK = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]")

# Match knowledge.gardener._slugify byte-for-byte.
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text_in: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_in)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug or "note"


def _code_spans(body: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of fenced and inline code regions."""
    spans: list[tuple[int, int]] = []
    for match in _FENCED.finditer(body):
        spans.append(match.span())
    for match in _INLINE.finditer(body):
        # Inline-code spans inside fenced spans would be redundant but harmless;
        # the only consumer is `_in_span`, which treats spans as a flat union.
        spans.append(match.span())
    return spans


def _in_span(pos: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def unlinkify(body: str, target_slugs: Iterable[str]) -> str:
    """Replace ``[[X]]`` / ``[[X|Y]]`` with bare text where ``slug(X)`` matches.

    Anchors (``#section`` and ``^block``) are stripped from the target before
    slugifying *and* from the replacement text. Display text (the part after
    ``|``) wins when present. Wikilinks inside fenced or inline code regions
    are preserved verbatim.
    """
    slug_set = frozenset(target_slugs)
    if not slug_set:
        return body
    spans = _code_spans(body)

    def replace(match: re.Match[str]) -> str:
        if _in_span(match.start(), spans):
            return match.group(0)
        target_raw = match.group(1).strip()
        target_no_anchor = re.split(r"[#^]", target_raw, maxsplit=1)[0].strip()
        if _slugify(target_no_anchor) not in slug_set:
            return match.group(0)
        display = match.group(2)
        if display is not None:
            return display.strip()
        return target_no_anchor

    return _WIKILINK.sub(replace, body)


def unlinkify_if_changed(body: str, target_slugs: Iterable[str]) -> str | None:
    """Like :func:`unlinkify` but return None when the body is unchanged.

    Lets callers skip a database write when no replacement happened.
    """
    new_body = unlinkify(body, target_slugs)
    if new_body == body:
        return None
    return new_body

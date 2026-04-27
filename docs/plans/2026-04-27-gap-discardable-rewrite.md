# Discardable-Gap Source Rewrite + Tombstone Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the loop on `triaged: discardable` gap stubs by having the gardener (a) rewrite the wikilinks in source notes that refer to them and (b) tombstone the gap row + stub once no references remain — eliminating the stub-regeneration cycle the triage script currently works around.

**Architecture:** Extend `knowledge.gaps.discover_gaps` with two new branches keyed off stub frontmatter. Phase A (rewrite): for any slug whose stub is marked `triaged: discardable`, replace `[[X]]` → bare text in the body of every source note in `referenced_by`, then skip the usual `write_stub` refresh. Phase B (tombstone): after the main loop, delete Gap rows + stubs whose slug is no longer present in `slug_refs` AND whose stub was marked discardable. The reconciler's content-hash detection re-ingests rewritten notes on the next gardener cycle, naturally emptying `note_links` and unlocking tombstone — no manual `note_links` mutation. Source-note rewrite is gated behind `KNOWLEDGE_GAPS_REWRITE_DISCARDABLE` (default off, logs dry-run counts) for first-cycle observability.

**Tech Stack:** Python 3.x, SQLAlchemy/SQLModel, PyYAML, pytest. New regex tracking the same shape as `knowledge/links.py:_WIKILINK`. No new external dependencies.

---

## Context: where the existing pieces are

| Piece                         | Location                                                                 | What it does                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Wikilink regex (extraction)   | `projects/monolith/knowledge/links.py:8-10`                              | `_FENCED`, `_INLINE`, `_WIKILINK` — strip code, then match `[[target]]` and `[[target\|display]]` |
| `discover_gaps`               | `projects/monolith/knowledge/gaps.py:74`                                 | Full-scan: builds `slug_refs` from `note_links`, upserts Gap rows, calls `write_stub`             |
| `_slugify`                    | `projects/monolith/knowledge/gardener.py:182` (re-imported by `gaps.py`) | Title → slug conversion                                                                           |
| Stub frontmatter parsing      | `projects/monolith/knowledge/gap_stubs.py:83` (`parse_stub_frontmatter`) | Returns `dict` of frontmatter                                                                     |
| `triaged: discardable` writer | `tools/knowledge_research/bin/triage-stubs.sh:163-176`                   | awk-edits stub frontmatter                                                                        |
| `Note.path`                   | `projects/monolith/knowledge/models.py:60`                               | unique disk path; `vault_root / note.path` is the file                                            |
| Reconciler ingest             | `projects/monolith/knowledge/reconciler.py:307-317`                      | `links.extract` + `store.upsert_note(..., links=note_links)` rebuilds `NoteLink` rows             |
| Gardener orchestration        | `projects/monolith/knowledge/gardener.py:411` (`_discover_gaps` call)    | Runs reconciler first, then `discover_gaps`                                                       |

**Existing comment that motivates this plan** (`triage-stubs.sh:188-192`):

> Marking instead of deleting prevents the gap-detector from re-creating them (the classifier doesn't check aliases on canonical atoms, so a deleted stub gets regenerated on the next gap-detection cycle). The marker is invisible to gap-detector (which is create-if-not-exists) and to the wrapper's eligibility loop.

---

## Task 1: Pure `unlinkify` function (TDD)

**Files:**

- Create: `projects/monolith/knowledge/gap_unlinkify.py`
- Create: `projects/monolith/knowledge/gap_unlinkify_test.py`

**Step 1.1: Write failing tests**

Tests must cover: bare link, aliased link, heading anchor, code-fence skip, inline-code skip, slug-variant matching (`[[Bayes' Theorem]]` slugs to same id as `[[bayes theorem]]`), unrelated wikilinks left alone, no-op when nothing matches, no trailing whitespace introduced.

````python
# projects/monolith/knowledge/gap_unlinkify_test.py
"""Tests for gap_unlinkify — replace [[X]] with bare text where slug(X) matches."""
from __future__ import annotations

from knowledge.gap_unlinkify import unlinkify


def test_bare_link_replaced_with_target_text():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, {"bayes-theorem"}) == "We use Bayes' Theorem heavily."


def test_aliased_link_replaced_with_display_text():
    body = "We use [[Bayes' Theorem|Bayes]] heavily."
    assert unlinkify(body, {"bayes-theorem"}) == "We use Bayes heavily."


def test_heading_anchor_dropped_in_replacement():
    body = "See [[Bayes' Theorem#Derivation]] for details."
    assert unlinkify(body, {"bayes-theorem"}) == "See Bayes' Theorem for details."


def test_block_anchor_dropped_in_replacement():
    body = "See [[Note^para1]] above."
    assert unlinkify(body, {"note"}) == "See Note above."


def test_unrelated_wikilinks_preserved():
    body = "We use [[Bayes' Theorem]] not [[Frequentism]]."
    assert unlinkify(body, {"bayes-theorem"}) == "We use Bayes' Theorem not [[Frequentism]]."


def test_fenced_code_block_left_untouched():
    body = "Prose [[Foo]] here.\n\n```\ncode [[Foo]] inside\n```\n"
    out = unlinkify(body, {"foo"})
    assert "Prose Foo here." in out
    assert "code [[Foo]] inside" in out  # fenced — preserved


def test_inline_code_left_untouched():
    body = "Prose [[Foo]] but `inline [[Foo]]` stays."
    out = unlinkify(body, {"foo"})
    assert "Prose Foo but" in out
    assert "`inline [[Foo]]`" in out


def test_no_match_returns_input_unchanged():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, {"frequentism"}) == body


def test_empty_slugs_set_is_no_op():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, set()) == body


def test_repeated_link_all_replaced():
    body = "[[Foo]] then [[Foo]] then [[Foo|foo]]."
    assert unlinkify(body, {"foo"}) == "Foo then Foo then foo."


def test_returns_none_when_no_change(monkeypatch):
    """unlinkify_if_changed returns None on no-op (caller skips write)."""
    from knowledge.gap_unlinkify import unlinkify_if_changed
    body = "Plain prose, no links."
    assert unlinkify_if_changed(body, {"foo"}) is None
````

**Step 1.2: Run tests, verify all fail with import error**

Run: `cd /tmp/claude-worktrees/gap-discardable-rewrite && python -m pytest projects/monolith/knowledge/gap_unlinkify_test.py -v 2>&1 | head -30`
Expected: ImportError: No module named 'knowledge.gap_unlinkify'

**Step 1.3: Implement minimal `gap_unlinkify.py`**

````python
# projects/monolith/knowledge/gap_unlinkify.py
"""Replace [[X]] wikilinks with bare text when slug(X) matches a target set.

Mirrors the extraction semantics of knowledge.links.extract:
  * Skip fenced (```...```) and inline (`...`) code regions.
  * Match [[target]] and [[target|display]] forms.
  * Strip heading (#) and block (^) anchors before slugifying.

Replacement rules:
  * [[X]]      -> X (raw target text, anchors dropped)
  * [[X|Y]]    -> Y (display text wins)

Used by knowledge.gaps.discover_gaps to clean up source notes that point
at gap stubs which the user has triaged as `triaged: discardable`. The
intent is to make those wikilinks go away so the gap-discovery pass on
the next cycle no longer registers them — closing the regeneration
loop the triage script currently mitigates by marking instead of
deleting.
"""
from __future__ import annotations

import re
from typing import Iterable

# Reuse the shape from knowledge.links so extraction and rewrite stay aligned.
_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_WIKILINK = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]")
_ANCHOR_SPLIT = re.compile(r"[#^]")


def _slugify(text_in: str) -> str:
    """Title-cased text -> kebab-case slug. Mirrors gardener._slugify exactly."""
    # Local copy to avoid a circular import with knowledge.gardener; the
    # gardener also imports from knowledge.gaps. The gaps module already
    # uses the same approach (lazy import). Both implementations MUST
    # produce identical output — covered by gap_unlinkify_test.
    text_in = text_in.strip().lower()
    text_in = re.sub(r"[^a-z0-9]+", "-", text_in)
    return text_in.strip("-")


def unlinkify(body: str, target_slugs: Iterable[str]) -> str:
    """Return ``body`` with matching ``[[X]]`` wikilinks replaced by bare text.

    A wikilink ``[[X]]`` (or ``[[X|Y]]``) is rewritten when ``_slugify(X)``
    (after stripping any ``#anchor`` / ``^block``) is in ``target_slugs``.
    Code regions (fenced and inline) are left untouched.
    """
    slug_set = set(target_slugs)
    if not slug_set:
        return body

    # Build a mask of code-region spans so the replacement step can skip them.
    # We can't simply substring-replace, because the same match shape may
    # appear inside code (preserve) and outside code (rewrite).
    code_spans: list[tuple[int, int]] = []
    for pat in (_FENCED, _INLINE):
        for m in pat.finditer(body):
            code_spans.append(m.span())

    def _in_code(start: int, end: int) -> bool:
        for cs, ce in code_spans:
            if start >= cs and end <= ce:
                return True
        return False

    def _replace(match: re.Match[str]) -> str:
        if _in_code(match.start(), match.end()):
            return match.group(0)
        target = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else None
        target_no_anchor = _ANCHOR_SPLIT.split(target, maxsplit=1)[0].strip()
        if _slugify(target_no_anchor) not in slug_set:
            return match.group(0)
        return display if display else target_no_anchor

    return _WIKILINK.sub(_replace, body)


def unlinkify_if_changed(body: str, target_slugs: Iterable[str]) -> str | None:
    """Return rewritten body, or ``None`` if no change. Lets callers skip writes."""
    out = unlinkify(body, target_slugs)
    return None if out == body else out
````

**Step 1.4: Run tests, verify all pass**

Run: `cd /tmp/claude-worktrees/gap-discardable-rewrite && python -m pytest projects/monolith/knowledge/gap_unlinkify_test.py -v`
Expected: all green.

**Step 1.5: Verify slug parity with gardener**

Add one test asserting `unlinkify._slugify` returns the same result as `gardener._slugify` for a representative input set.

```python
def test_slugify_matches_gardener():
    from knowledge.gap_unlinkify import _slugify as ours
    from knowledge.gardener import _slugify as theirs
    for s in ["Bayes' Theorem", "Foo Bar", "Already-Slug", "  Mixed/Case! "]:
        assert ours(s) == theirs(s), f"divergence on {s!r}"
```

Run: `python -m pytest projects/monolith/knowledge/gap_unlinkify_test.py::test_slugify_matches_gardener -v`
Expected: PASS.

**Step 1.6: Commit**

```bash
cd /tmp/claude-worktrees/gap-discardable-rewrite
git add projects/monolith/knowledge/gap_unlinkify.py projects/monolith/knowledge/gap_unlinkify_test.py
git commit -m "feat(knowledge): add gap_unlinkify for source-note wikilink rewrites"
```

---

## Task 2: Stub-state predicate

**Files:**

- Modify: `projects/monolith/knowledge/gap_unlinkify.py` (append helper)
- Modify: `projects/monolith/knowledge/gap_unlinkify_test.py` (append tests)

**Step 2.1: Write failing tests**

```python
def test_is_discardable_true(tmp_path):
    from knowledge.gap_unlinkify import is_discardable
    stub = tmp_path / "foo.md"
    stub.write_text("---\nid: foo\ntype: gap\ntriaged: discardable\n---\n\nbody\n")
    assert is_discardable(stub) is True


def test_is_discardable_false_when_keep(tmp_path):
    from knowledge.gap_unlinkify import is_discardable
    stub = tmp_path / "foo.md"
    stub.write_text("---\nid: foo\ntriaged: keep\n---\n\nbody\n")
    assert is_discardable(stub) is False


def test_is_discardable_false_when_unmarked(tmp_path):
    from knowledge.gap_unlinkify import is_discardable
    stub = tmp_path / "foo.md"
    stub.write_text("---\nid: foo\n---\n\nbody\n")
    assert is_discardable(stub) is False


def test_is_discardable_false_when_missing(tmp_path):
    from knowledge.gap_unlinkify import is_discardable
    assert is_discardable(tmp_path / "nope.md") is False


def test_is_discardable_false_on_malformed_frontmatter(tmp_path):
    from knowledge.gap_unlinkify import is_discardable
    stub = tmp_path / "bad.md"
    stub.write_text("not frontmatter at all\n")
    assert is_discardable(stub) is False
```

**Step 2.2: Run tests, verify fail**

Run: `python -m pytest projects/monolith/knowledge/gap_unlinkify_test.py -v -k discardable`
Expected: AttributeError: module 'knowledge.gap_unlinkify' has no attribute 'is_discardable'.

**Step 2.3: Implement `is_discardable`**

Append to `gap_unlinkify.py`:

```python
from pathlib import Path
import yaml


def is_discardable(stub_path: Path) -> bool:
    """Return True iff the stub frontmatter has ``triaged: discardable``.

    Defensive on malformed inputs (missing file, no frontmatter, YAML
    error, non-dict frontmatter) — all return False rather than raise.
    The triage marker is purely advisory; an unparseable stub is treated
    as not-discardable so we never erase source links based on bad data.
    """
    try:
        text = stub_path.read_text()
    except (FileNotFoundError, OSError):
        return False
    if not text.startswith("---\n"):
        return False
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return False
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return False
    if not isinstance(meta, dict):
        return False
    return meta.get("triaged") == "discardable"
```

**Step 2.4: Run tests, verify pass**

Run: `python -m pytest projects/monolith/knowledge/gap_unlinkify_test.py -v -k discardable`
Expected: all green.

**Step 2.5: Commit**

```bash
git add projects/monolith/knowledge/gap_unlinkify.py projects/monolith/knowledge/gap_unlinkify_test.py
git commit -m "feat(knowledge): add is_discardable predicate for triaged stubs"
```

---

## Task 3: Wire Phase A (rewrite) into `discover_gaps` behind feature flag

**Files:**

- Modify: `projects/monolith/knowledge/gaps.py:74-232` (`discover_gaps`)
- Create: `projects/monolith/knowledge/gap_discardable_rewrite_test.py`

**Step 3.1: Write failing integration test**

```python
# projects/monolith/knowledge/gap_discardable_rewrite_test.py
"""End-to-end: discover_gaps rewrites source notes for discardable stubs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

# These fixtures must mirror what gap_lifecycle_test.py / gap_end_to_end_test.py
# already use. Reuse the same conftest.py session/vault fixtures.


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_discardable_stub_rewrites_source_when_flag_on(
    monkeypatch, tmp_vault, knowledge_session
):
    """Phase A: when KNOWLEDGE_GAPS_REWRITE_DISCARDABLE=1 and stub has
    triaged: discardable, source notes are rewritten and write_stub is skipped."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault
    # Source atom containing a body link to the gap.
    src_path = vault / "_processed" / "source-atom.md"
    _write(src_path, (
        "---\nid: source-atom\ntitle: Source Atom\ntype: atom\n---\n\n"
        "We use [[Discardable Concept]] often.\n"
    ))
    # Pre-existing discardable stub.
    stub_path = vault / "_researching" / "discardable-concept.md"
    _write(stub_path, (
        "---\nid: discardable-concept\ntitle: Discardable Concept\n"
        "type: gap\nstatus: discovered\ntriaged: discardable\n---\n\n"
    ))
    # Pre-populate Note + NoteLink rows for the source so discover_gaps sees the link.
    _ingest_for_test(knowledge_session, vault, src_path)

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    rewritten = src_path.read_text()
    assert "[[Discardable Concept]]" not in rewritten
    assert "We use Discardable Concept often." in rewritten

    # Stub is NOT refreshed (mtime / content preserved); referenced_by absent.
    stub_after = yaml.safe_load(stub_path.read_text().split("---\n", 2)[1])
    assert stub_after.get("referenced_by") is None  # write_stub was skipped


def test_discardable_stub_dry_run_when_flag_off(
    monkeypatch, tmp_vault, knowledge_session
):
    """Without the flag, discover_gaps logs but does not mutate source notes."""
    monkeypatch.delenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", raising=False)
    vault = tmp_vault
    src_path = vault / "_processed" / "source-atom.md"
    body = ("---\nid: source-atom\ntitle: Source\ntype: atom\n---\n\n"
            "We use [[Discardable Concept]] often.\n")
    _write(src_path, body)
    _write(vault / "_researching" / "discardable-concept.md", (
        "---\nid: discardable-concept\ntype: gap\ntriaged: discardable\n---\n\n"
    ))
    _ingest_for_test(knowledge_session, vault, src_path)

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    assert src_path.read_text() == body  # untouched


def test_non_discardable_stub_unaffected(
    monkeypatch, tmp_vault, knowledge_session
):
    """Stubs without the marker behave exactly as they do today (write_stub refresh)."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault
    src_path = vault / "_processed" / "src.md"
    body = ("---\nid: src\ntype: atom\n---\n\n[[Real Concept]] is interesting.\n")
    _write(src_path, body)
    _ingest_for_test(knowledge_session, vault, src_path)

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    # Source untouched; stub created normally.
    assert src_path.read_text() == body
    new_stub = vault / "_researching" / "real-concept.md"
    assert new_stub.exists()
    fm = yaml.safe_load(new_stub.read_text().split("---\n", 2)[1])
    assert fm.get("referenced_by") == ["src"]
```

`_ingest_for_test` is a small fixture helper that runs the reconciler ingest path on a single file. If a similar helper doesn't exist, copy the minimal upsert-Note-and-NoteLinks shape from `gap_end_to_end_test.py`'s setup (which has the same need). **Investigate before writing — don't duplicate if a helper exists.**

**Step 3.2: Run tests, verify fail**

Run: `python -m pytest projects/monolith/knowledge/gap_discardable_rewrite_test.py -v`
Expected: tests fail (source still contains `[[...]]`, behavior not implemented).

**Step 3.3: Modify `discover_gaps` to add Phase A**

In `projects/monolith/knowledge/gaps.py`, around line 168 (the `for slug, refs in slug_refs.items():` loop):

1. **Above** the loop, add an env-flag read and a "discardable rewrite" counter:

   ```python
   rewrite_enabled = os.environ.get("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "").lower() in {"1", "true", "yes"}
   rewrites_applied = 0
   rewrites_dryrun = 0
   ```

2. **Inside** the loop, before the `existing = existing_by_note_id.get(slug)` line, peek at the stub:

   ```python
   stub_path = stub_dir / f"{slug}.md"
   if is_discardable(stub_path) and refs_sorted:
       changed_paths = _rewrite_sources(session, vault_root, slug, refs_sorted, dry_run=not rewrite_enabled)
       if rewrite_enabled:
           rewrites_applied += changed_paths
       else:
           rewrites_dryrun += changed_paths
       continue  # Skip the normal upsert + write_stub path for discardable stubs.
   ```

3. Add a private helper `_rewrite_sources` to `gaps.py`:

   ```python
   def _rewrite_sources(
       session: Session,
       vault_root: Path,
       slug: str,
       source_note_ids: list[str],
       *,
       dry_run: bool,
   ) -> int:
       """Rewrite [[X]] -> bare text in source notes. Returns count touched."""
       rows = session.execute(
           select(Note.note_id, Note.path).where(Note.note_id.in_(source_note_ids))
       ).all()
       touched = 0
       for note_id, rel_path in rows:
           abs_path = vault_root / rel_path
           try:
               body = abs_path.read_text()
           except (FileNotFoundError, OSError):
               continue
           new_body = unlinkify_if_changed(body, {slug})
           if new_body is None:
               continue
           touched += 1
           if not dry_run:
               abs_path.write_text(new_body)
       return touched
   ```

4. Add the import at the top of `gaps.py`:

   ```python
   from knowledge.gap_unlinkify import is_discardable, unlinkify_if_changed
   ```

   plus `import os`.

5. Update the final `logger.info(...)` to include rewrite counts:
   ```python
   if new_items or backfilled or rewrites_applied or rewrites_dryrun:
       logger.info(
           "gaps.discover_gaps: inserted=%d backfilled_note_id=%d "
           "stubs_written=%d rewrites_applied=%d rewrites_dryrun=%d",
           inserted, backfilled, stubs_written, rewrites_applied, rewrites_dryrun,
       )
   ```

**Step 3.4: Run tests, verify pass**

Run: `python -m pytest projects/monolith/knowledge/gap_discardable_rewrite_test.py -v`
Expected: all three tests pass.

**Step 3.5: Run the existing gap test suite to confirm no regressions**

Run: `python -m pytest projects/monolith/knowledge/gap*_test.py projects/monolith/knowledge/gardener_test.py -v 2>&1 | tail -40`
Expected: all pre-existing tests still pass.

**Step 3.6: Commit**

```bash
git add projects/monolith/knowledge/gaps.py projects/monolith/knowledge/gap_discardable_rewrite_test.py
git commit -m "feat(knowledge): rewrite source wikilinks for discardable gap stubs

Behind KNOWLEDGE_GAPS_REWRITE_DISCARDABLE flag (default off, dry-run logs
the would-rewrite count). When stub frontmatter has triaged: discardable,
discover_gaps replaces [[X]] -> bare text in every source note in
referenced_by and skips the write_stub refresh."
```

---

## Task 4: Phase B (tombstone) — delete gap row + stub when no refs remain

**Files:**

- Modify: `projects/monolith/knowledge/gaps.py` (append tombstone phase to `discover_gaps`)
- Modify: `projects/monolith/knowledge/gap_discardable_rewrite_test.py` (add tombstone tests)

**Step 4.1: Write failing tests**

```python
def test_tombstone_removes_gap_when_refs_gone(
    monkeypatch, tmp_vault, knowledge_session
):
    """Phase B: after sources are clean, the next discover_gaps cycle
    deletes the Gap row and the stub file."""
    from knowledge.models import Gap
    from sqlalchemy import select

    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault
    # Pre-existing Gap row + discardable stub, but NO source notes
    # reference it (simulating "post-rewrite" state).
    knowledge_session.add(Gap(term="discardable", note_id="discardable", state="discovered"))
    knowledge_session.commit()
    stub_path = vault / "_researching" / "discardable.md"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text("---\nid: discardable\ntype: gap\ntriaged: discardable\n---\n\n")

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    rows = knowledge_session.execute(select(Gap).where(Gap.note_id == "discardable")).scalars().all()
    assert rows == []
    assert not stub_path.exists()


def test_tombstone_preserves_keep_marked_stubs_with_no_refs(
    monkeypatch, tmp_vault, knowledge_session
):
    """A 'keep' stub with no refs is not tombstoned — only discardable is."""
    from knowledge.models import Gap
    from sqlalchemy import select

    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault
    knowledge_session.add(Gap(term="kept", note_id="kept", state="discovered"))
    knowledge_session.commit()
    stub_path = vault / "_researching" / "kept.md"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text("---\nid: kept\ntype: gap\ntriaged: keep\n---\n\n")

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    rows = knowledge_session.execute(select(Gap).where(Gap.note_id == "kept")).scalars().all()
    assert len(rows) == 1
    assert stub_path.exists()


def test_tombstone_preserves_unmarked_stubs_with_no_refs(
    monkeypatch, tmp_vault, knowledge_session
):
    """A stub without any triage marker is not tombstoned."""
    from knowledge.models import Gap
    from sqlalchemy import select

    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault
    knowledge_session.add(Gap(term="orphan", note_id="orphan", state="discovered"))
    knowledge_session.commit()
    stub_path = vault / "_researching" / "orphan.md"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text("---\nid: orphan\ntype: gap\n---\n\n")

    from knowledge.gaps import discover_gaps
    discover_gaps(knowledge_session, vault)

    rows = knowledge_session.execute(select(Gap).where(Gap.note_id == "orphan")).scalars().all()
    assert len(rows) == 1
    assert stub_path.exists()
```

**Step 4.2: Run tests, verify fail**

Run: `python -m pytest projects/monolith/knowledge/gap_discardable_rewrite_test.py -v -k tombstone`
Expected: tests fail (gap rows still present after `discover_gaps`).

**Step 4.3: Implement tombstone phase in `discover_gaps`**

After the main `for slug, refs in slug_refs.items():` loop and the existing `session.commit()` (around line 224), add:

```python
# Phase B: tombstone discardable gaps with no remaining refs.
#
# A Gap row whose note_id is NOT in this cycle's slug_refs has zero
# inbound wikilinks (note_links was the source of truth above). For
# such rows, if the stub is marked triaged: discardable, the user
# has signalled "this concept is closed" — delete the row and the
# stub file together. If the stub is missing or marked otherwise,
# leave both alone.
tombstoned = 0
present_slugs = set(slug_refs.keys())
for gap in all_gaps:
    if not gap.note_id or gap.note_id in present_slugs:
        continue
    stub_for_gap = stub_dir / f"{gap.note_id}.md"
    if not is_discardable(stub_for_gap):
        continue
    session.delete(gap)
    try:
        stub_for_gap.unlink()
    except FileNotFoundError:
        pass  # already gone, idempotent
    tombstoned += 1

if tombstoned:
    session.commit()
```

Update the trailing log line to include `tombstoned=%d`.

**Step 4.4: Run tests, verify pass**

Run: `python -m pytest projects/monolith/knowledge/gap_discardable_rewrite_test.py -v`
Expected: all (rewrite + tombstone) green.

**Step 4.5: Run full gap test suite for regressions**

Run: `python -m pytest projects/monolith/knowledge/gap*_test.py projects/monolith/knowledge/gardener_test.py projects/monolith/knowledge/reconciler*_test.py -v 2>&1 | tail -30`
Expected: pass.

**Step 4.6: Commit**

```bash
git add projects/monolith/knowledge/gaps.py projects/monolith/knowledge/gap_discardable_rewrite_test.py
git commit -m "feat(knowledge): tombstone discardable gap rows + stubs when refs cleared

After Phase A rewrites source notes, the next discover_gaps cycle finds
the slug absent from note_links. For Gap rows whose stub is marked
triaged: discardable, delete the row and the stub file. Stubs with
keep/unmarked status remain untouched."
```

---

## Task 5: End-to-end two-cycle convergence test

**Files:**

- Modify: `projects/monolith/knowledge/gap_discardable_rewrite_test.py`

**Step 5.1: Write the convergence test**

```python
def test_two_cycle_convergence(
    monkeypatch, tmp_vault, knowledge_session, run_reconciler  # fixture
):
    """Cycle 1: discover_gaps rewrites source.
       (Reconciler re-ingests rewritten source -> note_links cleared.)
       Cycle 2: discover_gaps tombstones gap row + stub.
    """
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    vault = tmp_vault

    src_path = vault / "_processed" / "src.md"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(
        "---\nid: src\ntype: atom\n---\n\nWe use [[Throwaway]] sometimes.\n"
    )
    stub_path = vault / "_researching" / "throwaway.md"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_path.write_text(
        "---\nid: throwaway\ntype: gap\ntriaged: discardable\n---\n\n"
    )

    # Initial reconcile populates Note + NoteLink for src.md.
    run_reconciler(knowledge_session, vault)

    from knowledge.gaps import discover_gaps
    from knowledge.models import Gap
    from sqlalchemy import select

    # Cycle 1: rewrites the source note.
    discover_gaps(knowledge_session, vault)
    assert "[[Throwaway]]" not in src_path.read_text()
    # Gap row still present (created in this cycle by upstream code, or
    # absent — either way, stub still exists since we skipped write_stub).
    assert stub_path.exists()

    # Reconciler picks up the rewrite (hash changed) and rebuilds note_links.
    run_reconciler(knowledge_session, vault)

    # Cycle 2: with no remaining refs, tombstone fires.
    discover_gaps(knowledge_session, vault)
    rows = knowledge_session.execute(select(Gap).where(Gap.note_id == "throwaway")).scalars().all()
    assert rows == []
    assert not stub_path.exists()
```

`run_reconciler` is a fixture that runs the production reconciler against the test vault — copy from `reconciler_test.py` if not already in `conftest.py`.

**Step 5.2: Run test, verify pass**

Run: `python -m pytest projects/monolith/knowledge/gap_discardable_rewrite_test.py::test_two_cycle_convergence -v`
Expected: pass.

**Step 5.3: Commit**

```bash
git add projects/monolith/knowledge/gap_discardable_rewrite_test.py
git commit -m "test(knowledge): two-cycle convergence for discardable gap cleanup"
```

---

## Task 6: Update `triage-stubs.sh` comment + README

**Files:**

- Modify: `tools/knowledge_research/bin/triage-stubs.sh:188-192` (rewrite the rationale comment now that the workaround is no longer the workaround)
- Modify: `projects/monolith/knowledge/README.md` (if a gap-lifecycle section exists)

**Step 6.1: Update the comment**

Replace the existing `triage-stubs.sh:188-192` block with:

```bash
# `triaged: discardable` for stubs the user can clean up at any time.
# discover_gaps detects this marker and (when KNOWLEDGE_GAPS_REWRITE_DISCARDABLE=1)
# rewrites [[X]] -> bare text in every source note that referenced the
# stub, then tombstones the gap row + stub file once no references
# remain. The marker is effectively a "delete this gap, and the
# concept along with it" instruction to the gardener.
```

**Step 6.2: README update (if applicable)**

Run: `grep -n "discardable\|triage" projects/monolith/knowledge/README.md`

If the README mentions `triaged` or the gap lifecycle, add a paragraph on the new behavior. If it doesn't, skip this step — don't manufacture documentation.

**Step 6.3: Commit**

```bash
git add tools/knowledge_research/bin/triage-stubs.sh projects/monolith/knowledge/README.md
git commit -m "docs(knowledge): note discardable rewrite + tombstone in triage script"
```

---

## Task 7: Push, watch CI, enable the flag in deploy values

**Step 7.1: Push branch and open PR**

```bash
cd /tmp/claude-worktrees/gap-discardable-rewrite
git push -u origin feat/gap-discardable-rewrite
gh pr create --title "feat(knowledge): rewrite + tombstone discardable gap stubs" --body "$(cat <<'EOF'
## Summary
- Adds `gap_unlinkify` module (pure function: `[[X]]` -> bare text where slug matches)
- Extends `discover_gaps` with two phases gated on `triaged: discardable` stub frontmatter:
  - **Phase A:** rewrite source notes (behind `KNOWLEDGE_GAPS_REWRITE_DISCARDABLE` flag)
  - **Phase B:** tombstone gap row + stub once `note_links` no longer references the slug
- Closes the regeneration loop the triage script previously worked around by marking instead of deleting

## Test plan
- [x] Unit tests for `unlinkify` (bare/aliased/anchor/code-fence/no-match)
- [x] `is_discardable` predicate tests (frontmatter, malformed, missing)
- [x] Phase A integration: rewrite when flag on, dry-run when flag off, no-op when not discardable
- [x] Phase B integration: tombstone discardable, preserve keep/unmarked
- [x] End-to-end two-cycle convergence (reconciler in the loop)
EOF
)"
```

**Step 7.2: Watch CI**

```bash
gh pr checks <PR_NUMBER> --watch
```

If failures: read via `mcp__buildbuddy__get_invocation` (commitSha selector) → `get_target` → `get_log`. Fix and push.

**Step 7.3: Once green, flip the flag in `values.yaml`**

In a follow-up commit on the same PR (or a separate PR after this merges):

Modify `projects/monolith/deploy/values.yaml` — add:

```yaml
env:
  KNOWLEDGE_GAPS_REWRITE_DISCARDABLE: "1"
```

under the appropriate gardener/monolith section (find existing `env:` block).

Bump `projects/monolith/chart/Chart.yaml` version AND `projects/monolith/deploy/application.yaml` `targetRevision` together (CLAUDE.md anti-pattern: bumping one without the other).

Run a single gardener cycle in prod, observe `gaps.discover_gaps: ... rewrites_applied=N tombstoned=M` in logs (SigNoz), then re-watch on the next cycle that tombstone count grows as expected.

**Step 7.4: Merge**

```bash
gh pr merge --rebase
```

(Per CLAUDE.md: this repo only allows rebase merging.)

---

## Out of scope (intentionally not included)

- A separate "reconciler for stubs" job. The whole point is that `discover_gaps` already iterates everything we need; adding a parallel reconciler would duplicate state.
- Configurable replacement strategy ("keep as italic", "leave HTML comment"). User confirmed: fully clean.
- Backfill of pre-existing discardable stubs. The flag-gated rewrite handles them on the next cycle naturally.
- Removing the feature flag. Leave it for one or two cycles of observation; remove in a follow-up commit once the rewrite count matches expectations.

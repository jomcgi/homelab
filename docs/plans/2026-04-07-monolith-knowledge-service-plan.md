# Monolith Knowledge Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `knowledge` module to the monolith that reconciles `/vault/_processed/**/*.md` into a new `knowledge` Postgres schema (notes + chunks + links), with frontmatter promoted to filterable columns and voyage-4-nano embeddings stored alongside, scheduled by the existing `scheduler.scheduled_jobs` table.

**Architecture:** A new `knowledge/` Python package inside `projects/monolith/`, paired with a new `shared/` package that hosts the lifted markdown chunker (from `projects/obsidian_vault/vault_mcp/app/chunker.py`) and the lifted embedding client (from `projects/monolith/chat/embedding.py`). One Atlas migration creates the schema and registers the reconcile job. `knowledge/service.py` registers the handler with `shared/scheduler.py` at lifespan startup, following the same `on_startup(session)` convention as `home/service.py` and `shared/service.py`. All-or-nothing per-note transactions, lenient frontmatter parsing, content-hash-based diff.

**Tech Stack:** Python 3.12, SQLModel, pgvector + pgvector.sqlalchemy, PyYAML, FastAPI lifespan, Atlas migrations, BuildBuddy remote test (`bb remote test //... --config=ci`).

---

## Pre-flight

- Worktree: `/tmp/claude-worktrees/knowledge-service`
- Branch: `feat/knowledge-service`
- Design doc: `docs/plans/2026-04-07-monolith-knowledge-service-design.md`
- All tests run via `bb remote test //projects/monolith/<target>:<name> --config=ci` — never local pytest
- Commit messages: Conventional Commits + `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` trailer
- Run `format` after every code change before committing

---

### Task 1: Schema migration

**Files:**

- Create: `projects/monolith/chart/migrations/20260408000000_knowledge_schema.sql`
- Modify: `projects/monolith/chart/migrations/atlas.sum` (Atlas regenerates checksum)

**Step 1: Write the migration**

Copy the schema block from the design doc verbatim into the new file. The block ends with the `INSERT INTO scheduler.scheduled_jobs` upsert.

**Step 2: Regenerate `atlas.sum`**

Run from the worktree root:

```bash
cd projects/monolith && atlas migrate hash --dir "file://chart/migrations"
```

Expected: `atlas.sum` updated with one new line for the migration.

**Step 3: Verify the migrations configmap will pick it up**

Run:

```bash
helm template monolith projects/monolith/chart -f projects/monolith/deploy/values.yaml | grep -A2 "20260408000000_knowledge_schema"
```

Expected: the new file appears in the rendered `migrations-configmap` ConfigMap.

**Step 4: Commit**

```bash
git add projects/monolith/chart/migrations/20260408000000_knowledge_schema.sql projects/monolith/chart/migrations/atlas.sum
git commit -m "feat(monolith): add knowledge schema migration"
```

---

### Task 2: Lift `chunker.py` to `shared/`

The vault_mcp chunker has a vault-storage-specific API (it returns dicts with `content_hash`, `source_url`, `title`). We narrow it to a generic chunker that only knows about markdown text and chunks. Storage concerns become caller-side.

**Files:**

- Create: `projects/monolith/shared/chunker.py`
- Create: `projects/monolith/shared/chunker_test.py`
- Create: `projects/monolith/shared/__init__.py` (if missing)
- Reference (read only): `projects/obsidian_vault/vault_mcp/app/chunker.py`
- Reference (read only): `projects/obsidian_vault/vault_mcp/tests/chunker_test.py`

**Step 1: Read the source chunker**

Open `projects/obsidian_vault/vault_mcp/app/chunker.py` end-to-end. Note the public surface:

- `_split_by_headers(content)`
- `_split_paragraphs(text)`
- `chunk_markdown(content, content_hash, source_url, title, max_tokens=512, min_tokens=50)`

**Step 2: Write the failing test for the narrowed API**

`projects/monolith/shared/chunker_test.py`:

````python
"""Tests for the generic markdown chunker."""

from shared.chunker import Chunk, chunk_markdown


class TestChunkMarkdown:
    def test_empty_input_returns_empty_list(self):
        assert chunk_markdown("") == []

    def test_single_paragraph_one_chunk(self):
        chunks = chunk_markdown("Hello world.")
        assert len(chunks) == 1
        assert chunks[0]["index"] == 0
        assert chunks[0]["section_header"] == ""
        assert "Hello world." in chunks[0]["text"]

    def test_section_headers_carried_through(self):
        md = "# Top\n\nIntro.\n\n## Sub\n\nBody."
        chunks = chunk_markdown(md)
        headers = {c["section_header"] for c in chunks}
        assert "Top" in headers or "Sub" in headers

    def test_index_is_zero_based_and_dense(self):
        md = "# A\n\npara1\n\n## B\n\npara2\n\n## C\n\npara3"
        chunks = chunk_markdown(md)
        assert [c["index"] for c in chunks] == list(range(len(chunks)))

    def test_code_block_with_wikilinks_not_split(self):
        md = "Intro.\n\n```\n[[not_a_link]]\n# not a header\n```\n\nOutro."
        chunks = chunk_markdown(md)
        joined = " ".join(c["text"] for c in chunks)
        assert "[[not_a_link]]" in joined
````

**Step 3: Run test, expect import failure**

```bash
bb remote test //projects/monolith/shared:chunker_test --config=ci
```

Expected: FAIL — `shared.chunker` not found.

**Step 4: Write `shared/chunker.py`**

Port the source chunker, dropping `content_hash`/`source_url`/`title` parameters. Replace the dict return type with a `Chunk` `TypedDict` having keys `index`, `section_header`, `text`. Keep the heading-aware splitting and code-block handling logic verbatim.

Public API:

```python
from typing import TypedDict


class Chunk(TypedDict):
    index: int
    section_header: str
    text: str


def chunk_markdown(
    content: str,
    *,
    max_tokens: int = 512,
    min_tokens: int = 50,
) -> list[Chunk]:
    ...
```

**Step 5: Create / update BUILD.bazel for `shared/`**

`projects/monolith/shared/BUILD.bazel` may already exist (it hosts `scheduler.py` and `service.py`). Add `chunker.py` and `chunker_test.py` targets following the existing pattern. After editing, run `format` so gazelle reconciles deps.

**Step 6: Run test, expect pass**

```bash
bb remote test //projects/monolith/shared:chunker_test --config=ci
```

Expected: PASS.

**Step 7: Commit**

```bash
git add projects/monolith/shared/chunker.py projects/monolith/shared/chunker_test.py projects/monolith/shared/BUILD.bazel
git commit -m "feat(monolith): lift markdown chunker into shared/"
```

---

### Task 3: Lift `embedding.py` to `shared/`

The chat embedding client is already generic except for one hardcoded literal: the `voyage-4-nano` model name. We move it and parameterize that one knob. **All chat call sites are updated in the same commit** — no backwards-compat shim per CLAUDE.md.

**Files:**

- Create: `projects/monolith/shared/embedding.py`
- Create: `projects/monolith/shared/embedding_test.py`
- Modify: `projects/monolith/chat/embedding.py` → delete (callers retargeted)
- Modify: every file in `projects/monolith/chat/` that imports `chat.embedding`
- Modify: `projects/monolith/chat/BUILD.bazel`, `projects/monolith/shared/BUILD.bazel`

**Step 1: Inventory chat callers**

```bash
rg -n "from chat.embedding|import chat.embedding|chat\\.embedding" projects/monolith
```

Note every hit. Each will be retargeted to `from shared.embedding import EmbeddingClient`.

**Step 2: Inventory existing chat embedding tests**

```bash
ls projects/monolith/chat/embedding*_test.py
```

Each existing test moves to `projects/monolith/shared/` with the import path updated. Test names and bodies stay identical.

**Step 3: Write the failing new test for the `model` arg**

`projects/monolith/shared/embedding_test.py` (top of file, alongside the ported tests):

```python
def test_model_arg_is_sent_in_request_body(httpx_mock):
    """The constructor's `model` arg appears in the POST body."""
    httpx_mock.add_response(
        url="http://fake/v1/embeddings",
        json={"data": [{"embedding": [0.0] * 1024}]},
    )
    client = EmbeddingClient(base_url="http://fake", model="voyage-4-nano")
    asyncio.run(client.embed_batch(["hi"]))
    sent = httpx_mock.get_requests()[0]
    body = json.loads(sent.content)
    assert body["model"] == "voyage-4-nano"
```

(If existing tests already cover this, skip. Inspect first.)

**Step 4: Run test, expect import failure**

```bash
bb remote test //projects/monolith/shared:embedding_test --config=ci
```

Expected: FAIL — `shared.embedding` not found.

**Step 5: Move the file**

```bash
git mv projects/monolith/chat/embedding.py projects/monolith/shared/embedding.py
```

Edit `shared/embedding.py`:

- Constructor signature: `def __init__(self, *, base_url: str | None = None, model: str = "voyage-4-nano")`
- Replace the hardcoded `"model": "voyage-4-nano"` literal in the request body builder with `"model": self.model`
- Keep the existing 12-retry / 5-min budget logic, env var fallbacks, and async surface untouched

**Step 6: Move all existing chat embedding tests**

```bash
git mv projects/monolith/chat/embedding_*_test.py projects/monolith/shared/
```

Update the imports inside each moved test from `chat.embedding` to `shared.embedding`. No other changes.

**Step 7: Retarget every chat caller**

For each file from Step 1's inventory, replace `from chat.embedding import EmbeddingClient` with `from shared.embedding import EmbeddingClient`. Verify there are no remaining `chat.embedding` references:

```bash
rg -n "chat\\.embedding" projects/monolith
```

Expected: zero matches.

**Step 8: Update BUILD files**

- Remove `embedding.py` and `embedding_*_test.py` from `projects/monolith/chat/BUILD.bazel`
- Add them to `projects/monolith/shared/BUILD.bazel`
- Update `deps` of any chat target that previously depended on the chat embedding lib
- Run `format` to let gazelle reconcile the rest

**Step 9: Run all touched tests**

```bash
bb remote test //projects/monolith/shared:embedding_test //projects/monolith/chat/... --config=ci
```

Expected: PASS.

**Step 10: Commit**

```bash
git add -A projects/monolith/shared projects/monolith/chat
git commit -m "refactor(monolith): move embedding client to shared/ and parameterize model"
```

---

### Task 4: Frontmatter parser

**Files:**

- Create: `projects/monolith/knowledge/__init__.py`
- Create: `projects/monolith/knowledge/frontmatter.py`
- Create: `projects/monolith/knowledge/frontmatter_test.py`
- Create: `projects/monolith/knowledge/BUILD.bazel`

**Step 1: Write failing tests covering the full grid**

```python
"""Tests for lenient frontmatter parsing."""

from datetime import datetime, timezone

from knowledge.frontmatter import ParsedFrontmatter, parse


class TestParse:
    def test_no_frontmatter_returns_empty_metadata_and_full_body(self):
        meta, body = parse("Just a body.")
        assert meta == ParsedFrontmatter()
        assert body == "Just a body."

    def test_well_formed_frontmatter(self):
        raw = (
            "---\n"
            "title: Attention Is All You Need\n"
            "type: paper\n"
            "tags: [ml, attention]\n"
            "created: 2017-06-12\n"
            "---\n"
            "Body text."
        )
        meta, body = parse(raw)
        assert meta.title == "Attention Is All You Need"
        assert meta.type == "paper"
        assert meta.tags == ["ml", "attention"]
        assert meta.created == datetime(2017, 6, 12, tzinfo=timezone.utc)
        assert body == "Body text."

    def test_tags_as_comma_string(self):
        raw = "---\ntags: ml, attention,  transformers\n---\nx"
        meta, _ = parse(raw)
        assert meta.tags == ["ml", "attention", "transformers"]

    def test_tags_as_space_string(self):
        raw = "---\ntags: ml attention transformers\n---\nx"
        meta, _ = parse(raw)
        assert meta.tags == ["ml", "attention", "transformers"]

    def test_aliases_same_rules_as_tags(self):
        raw = "---\naliases: [Foo, Bar]\n---\nx"
        meta, _ = parse(raw)
        assert meta.aliases == ["Foo", "Bar"]

    def test_invalid_yaml_returns_empty_metadata_and_full_body(self):
        raw = "---\ntitle: [unterminated\n---\nBody text."
        meta, body = parse(raw)
        assert meta == ParsedFrontmatter()
        assert body == raw  # full original content, no body stripping

    def test_invalid_date_yields_none(self):
        raw = "---\ncreated: not-a-date\n---\nx"
        meta, _ = parse(raw)
        assert meta.created is None

    def test_unknown_keys_land_in_extra(self):
        raw = "---\ntitle: T\nauthor: Karpathy\nyear: 2017\n---\nx"
        meta, _ = parse(raw)
        assert meta.title == "T"
        assert meta.extra == {"author": "Karpathy", "year": 2017}

    def test_promoted_keys_never_appear_in_extra(self):
        raw = "---\ntype: paper\nstatus: published\nauthor: K\n---\nx"
        meta, _ = parse(raw)
        assert "type" not in meta.extra
        assert "status" not in meta.extra
        assert meta.extra == {"author": "K"}

    def test_delimiter_not_at_top_is_not_frontmatter(self):
        raw = "Body first.\n\n---\ntitle: T\n---\nMore body."
        meta, body = parse(raw)
        assert meta == ParsedFrontmatter()
        assert body == raw

    def test_up_ref_captured(self):
        raw = "---\nup: '[[Index]]'\n---\nx"
        meta, _ = parse(raw)
        assert meta.up_ref == "[[Index]]"
```

**Step 2: Run tests, expect failure**

```bash
bb remote test //projects/monolith/knowledge:frontmatter_test --config=ci
```

Expected: FAIL — module not found.

**Step 3: Implement `frontmatter.py`**

```python
"""Lenient YAML frontmatter parser for Obsidian-style notes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml

logger = logging.getLogger("monolith.knowledge.frontmatter")

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)

_PROMOTED_KEYS = {
    "title", "type", "status", "source",
    "tags", "aliases", "up", "created", "updated",
}


@dataclass
class ParsedFrontmatter:
    title: str | None = None
    type: str | None = None
    status: str | None = None
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    up_ref: str | None = None
    created: datetime | None = None
    updated: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse(raw: str) -> tuple[ParsedFrontmatter, str]:
    """Return (metadata, body). Errors degrade gracefully — never raise."""
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return ParsedFrontmatter(), raw
    block = match.group(1)
    body = raw[match.end():]
    try:
        data = yaml.safe_load(block) or {}
    except yaml.YAMLError as exc:
        logger.warning("frontmatter yaml error: %s", exc)
        return ParsedFrontmatter(), raw
    if not isinstance(data, dict):
        logger.warning("frontmatter is not a mapping: %r", type(data).__name__)
        return ParsedFrontmatter(), raw
    return _build(data), body


def _build(data: dict[str, Any]) -> ParsedFrontmatter:
    meta = ParsedFrontmatter()
    meta.title = _str_or_none(data.get("title"))
    meta.type = _str_or_none(data.get("type"))
    meta.status = _str_or_none(data.get("status"))
    meta.source = _str_or_none(data.get("source"))
    meta.tags = _string_list(data.get("tags"))
    meta.aliases = _string_list(data.get("aliases"))
    meta.up_ref = _str_or_none(data.get("up"))
    meta.created = _to_datetime(data.get("created"))
    meta.updated = _to_datetime(data.get("updated"))
    meta.extra = {k: v for k, v in data.items() if k not in _PROMOTED_KEYS}
    return meta


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


def _string_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        if "," in v:
            return [p.strip() for p in v.split(",") if p.strip()]
        return [p for p in v.split() if p]
    return []


def _to_datetime(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            logger.warning("invalid date in frontmatter: %r", v)
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    logger.warning("unparseable date type in frontmatter: %r", type(v).__name__)
    return None
```

**Step 4: Run tests, expect pass**

```bash
bb remote test //projects/monolith/knowledge:frontmatter_test --config=ci
```

Expected: PASS.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/__init__.py projects/monolith/knowledge/frontmatter.py projects/monolith/knowledge/frontmatter_test.py projects/monolith/knowledge/BUILD.bazel
git commit -m "feat(knowledge): add lenient frontmatter parser"
```

---

### Task 5: Wikilink extractor

**Files:**

- Create: `projects/monolith/knowledge/links.py`
- Create: `projects/monolith/knowledge/links_test.py`

**Step 1: Write failing tests**

````python
"""Tests for wikilink extraction."""

from knowledge.links import Link, extract


class TestExtract:
    def test_empty_body(self):
        assert extract("") == []

    def test_simple_link(self):
        assert extract("See [[Foo]].") == [Link(target="Foo", display=None)]

    def test_link_with_display(self):
        assert extract("See [[Foo|the foo]].") == [
            Link(target="Foo", display="the foo")
        ]

    def test_dedupe_preserves_first_order(self):
        body = "[[A]] then [[B]] then [[A]]"
        assert [l.target for l in extract(body)] == ["A", "B"]

    def test_fenced_code_block_excluded(self):
        body = "Intro [[Real]]\n\n```\n[[Fake]]\n```\n\nOutro [[AlsoReal]]"
        assert [l.target for l in extract(body)] == ["Real", "AlsoReal"]

    def test_inline_code_excluded(self):
        body = "Real [[A]] but `[[B]]` is code."
        assert [l.target for l in extract(body)] == ["A"]

    def test_unterminated_link_ignored(self):
        body = "[[unterminated and [[Real]]"
        assert [l.target for l in extract(body)] == ["Real"]
````

**Step 2: Run tests, expect failure**

```bash
bb remote test //projects/monolith/knowledge:links_test --config=ci
```

Expected: FAIL — module not found.

**Step 3: Implement `links.py`**

````python
"""Extract [[wikilinks]] from markdown bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_WIKILINK = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]")


@dataclass(frozen=True)
class Link:
    target: str
    display: str | None


def extract(body: str) -> list[Link]:
    stripped = _FENCED.sub("", body)
    stripped = _INLINE.sub("", stripped)
    seen: set[str] = set()
    out: list[Link] = []
    for match in _WIKILINK.finditer(stripped):
        target = match.group(1).strip()
        if not target or target in seen:
            continue
        seen.add(target)
        display = match.group(2).strip() if match.group(2) else None
        out.append(Link(target=target, display=display))
    return out
````

**Step 4: Run tests, expect pass**

```bash
bb remote test //projects/monolith/knowledge:links_test --config=ci
```

Expected: PASS.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/links.py projects/monolith/knowledge/links_test.py projects/monolith/knowledge/BUILD.bazel
git commit -m "feat(knowledge): add wikilink extractor"
```

---

### Task 6: Models + store

**Files:**

- Create: `projects/monolith/knowledge/models.py`
- Create: `projects/monolith/knowledge/store.py`
- Create: `projects/monolith/knowledge/store_test.py`

**Notes for executor:**

The SQLite test fixture pattern is in `projects/monolith/chat/store_test.py:14-34` — copy it verbatim. SQLite doesn't natively support `vector(1024)`, `TEXT[]`, or `JSONB`, but `pgvector.sqlalchemy.Vector` falls back to a generic column under SQLite, and SQLAlchemy handles `ARRAY`/`JSON` similarly. If the create_all step trips on these, fall back to `sqlalchemy.JSON` and `sqlalchemy.types.PickleType` for the SQLite test — but try the straightforward path first; the chat module's `chat/models.py:23` `Vector(1024)` works in the chat test fixture so this should too.

**Step 1: Write `models.py`**

```python
"""SQLModel definitions for the knowledge schema."""

import json
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from pydantic import field_validator
from sqlalchemy import ARRAY, JSON, Column, String
from sqlmodel import Field, SQLModel


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    path: str = Field(unique=True)
    title: str
    content_hash: str
    type: str | None = None
    status: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    aliases: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    up_ref: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    indexed_at: datetime | None = None


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    note_id: int = Field(foreign_key="knowledge.notes.id")
    chunk_index: int
    section_header: str = ""
    chunk_text: str
    embedding: list[float] = Field(sa_column=Column(Vector(1024)))

    @field_validator("embedding", mode="before")
    @classmethod
    def _parse_embedding(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v


class NoteLink(SQLModel, table=True):
    __tablename__ = "note_links"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    src_note_id: int = Field(foreign_key="knowledge.notes.id")
    target_path: str
    target_title: str | None = None
    kind: str  # 'up' | 'link'
```

**Step 2: Write failing store tests**

```python
"""Tests for KnowledgeStore."""

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.links import Link
from knowledge.models import Chunk, Note, NoteLink
from knowledge.store import KnowledgeStore


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def store(session):
    return KnowledgeStore(session=session)


def _meta(**kw):
    return ParsedFrontmatter(**kw)


def _chunks(n):
    return [
        {"index": i, "section_header": f"H{i}", "text": f"chunk {i}"}
        for i in range(n)
    ]


def _vecs(n):
    return [[float(i)] * 1024 for i in range(n)]


class TestGetIndexed:
    def test_empty(self, store):
        assert store.get_indexed() == {}

    def test_returns_path_to_hash_map(self, store):
        store.upsert_note(
            path="a.md",
            content_hash="h1",
            title="A",
            metadata=_meta(title="A"),
            chunks=_chunks(1),
            vectors=_vecs(1),
            links=[],
        )
        assert store.get_indexed() == {"a.md": "h1"}


class TestUpsertNote:
    def test_inserts_note_chunks_and_links(self, store, session):
        store.upsert_note(
            path="a.md",
            content_hash="h1",
            title="A",
            metadata=_meta(title="A", tags=["ml"]),
            chunks=_chunks(3),
            vectors=_vecs(3),
            links=[Link(target="B", display=None)],
        )
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].tags == ["ml"]
        chunks = list(session.scalars(select(Chunk)))
        assert len(chunks) == 3
        assert {c.chunk_index for c in chunks} == {0, 1, 2}
        links = list(session.scalars(select(NoteLink)))
        assert len(links) == 1
        assert links[0].target_path == "B"
        assert links[0].kind == "link"

    def test_re_upsert_replaces_chunk_count(self, store, session):
        store.upsert_note(
            path="a.md",
            content_hash="h1",
            title="A",
            metadata=_meta(title="A"),
            chunks=_chunks(5),
            vectors=_vecs(5),
            links=[],
        )
        store.upsert_note(
            path="a.md",
            content_hash="h2",
            title="A",
            metadata=_meta(title="A"),
            chunks=_chunks(2),
            vectors=_vecs(2),
            links=[],
        )
        chunks = list(session.scalars(select(Chunk)))
        assert len(chunks) == 2
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].content_hash == "h2"

    def test_up_ref_emits_link_with_kind_up(self, store, session):
        store.upsert_note(
            path="a.md",
            content_hash="h1",
            title="A",
            metadata=_meta(title="A", up_ref="[[Parent]]"),
            chunks=_chunks(1),
            vectors=_vecs(1),
            links=[],
        )
        links = list(session.scalars(select(NoteLink)))
        kinds = {l.kind for l in links}
        assert "up" in kinds


class TestDeleteNote:
    def test_cascade_removes_chunks_and_links(self, store, session):
        store.upsert_note(
            path="a.md",
            content_hash="h1",
            title="A",
            metadata=_meta(title="A"),
            chunks=_chunks(2),
            vectors=_vecs(2),
            links=[Link(target="B", display=None)],
        )
        store.delete_note("a.md")
        assert list(session.scalars(select(Note))) == []
        assert list(session.scalars(select(Chunk))) == []
        assert list(session.scalars(select(NoteLink))) == []
```

**Step 3: Run tests, expect failure**

```bash
bb remote test //projects/monolith/knowledge:store_test --config=ci
```

Expected: FAIL — store not found.

**Step 4: Implement `store.py`**

```python
"""Postgres data access layer for the knowledge schema."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, delete, select

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.links import Link
from knowledge.models import Chunk, Note, NoteLink
from shared.chunker import Chunk as ChunkPayload


class KnowledgeStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_indexed(self) -> dict[str, str]:
        rows = list(self.session.scalars(select(Note.path, Note.content_hash)))
        # scalars() flattens to first column; use session.execute for tuples
        result = self.session.execute(select(Note.path, Note.content_hash))
        return {path: ch for path, ch in result.all()}

    def upsert_note(
        self,
        *,
        path: str,
        content_hash: str,
        title: str,
        metadata: ParsedFrontmatter,
        chunks: list[ChunkPayload],
        vectors: list[list[float]],
        links: list[Link],
    ) -> None:
        # Delete existing row by path; cascades chunks + note_links.
        self.session.execute(delete(Note).where(Note.path == path))
        self.session.flush()

        note = Note(
            path=path,
            title=title,
            content_hash=content_hash,
            type=metadata.type,
            status=metadata.status,
            source=metadata.source,
            tags=metadata.tags,
            aliases=metadata.aliases,
            up_ref=metadata.up_ref,
            created_at=metadata.created,
            updated_at=metadata.updated,
            extra=metadata.extra,
            indexed_at=datetime.now(timezone.utc),
        )
        self.session.add(note)
        self.session.flush()

        for chunk, vector in zip(chunks, vectors, strict=True):
            self.session.add(
                Chunk(
                    note_id=note.id,
                    chunk_index=chunk["index"],
                    section_header=chunk["section_header"],
                    chunk_text=chunk["text"],
                    embedding=vector,
                )
            )

        for link in links:
            self.session.add(
                NoteLink(
                    src_note_id=note.id,
                    target_path=link.target,
                    target_title=link.display,
                    kind="link",
                )
            )
        if metadata.up_ref:
            self.session.add(
                NoteLink(
                    src_note_id=note.id,
                    target_path=metadata.up_ref,
                    target_title=None,
                    kind="up",
                )
            )

        self.session.commit()

    def delete_note(self, path: str) -> None:
        self.session.execute(delete(Note).where(Note.path == path))
        self.session.commit()
```

> **Note for executor:** the `get_indexed` body above shows two approaches because `session.scalars(select(col1, col2))` only returns the first column. Use the `session.execute(...).all()` form. Drop the dead `rows = ...` line before committing.

**Step 5: Run tests, expect pass**

```bash
bb remote test //projects/monolith/knowledge:store_test --config=ci
```

Expected: PASS. If the SQLite fallback chokes on `ARRAY(String)` or `JSON`, switch the offending columns to `Column(JSON)` and adjust the model — note that pgvector's `Vector` already works through this fixture in `chat/store_test.py` so it's a low risk.

**Step 6: Commit**

```bash
git add projects/monolith/knowledge/models.py projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py projects/monolith/knowledge/BUILD.bazel
git commit -m "feat(knowledge): add models and store"
```

---

### Task 7: Reconciler

**Files:**

- Create: `projects/monolith/knowledge/reconciler.py`
- Create: `projects/monolith/knowledge/reconciler_test.py`

**Step 1: Write failing tests**

The tests use a `tmp_path` vault and a fake `EmbeddingClient` that returns deterministic vectors and tracks call count. Cases (one test per case, names below):

- `test_empty_vault`
- `test_adds_one_file`
- `test_no_changes_skips_embedding`
- `test_edited_body_re_embeds`
- `test_edited_frontmatter_only_re_embeds`
- `test_deletes_removed_file`
- `test_broken_frontmatter_still_ingests`
- `test_partial_failure_persists_other_notes`
- `test_file_disappears_mid_cycle`

Sketch (full versions in implementation):

```python
"""Tests for the vault reconciler."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Chunk, Note
from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def embed_client():
    client = AsyncMock()
    client.embed_batch.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    return client


@pytest.fixture
def reconciler(session, embed_client, tmp_path):
    processed = tmp_path / "_processed"
    processed.mkdir()
    return Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=embed_client,
        vault_root=tmp_path,
    )


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / "_processed" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestReconciler:
    @pytest.mark.asyncio
    async def test_empty_vault(self, reconciler):
        result = await reconciler.run()
        assert result == (0, 0, 0)

    @pytest.mark.asyncio
    async def test_adds_one_file(self, reconciler, session, tmp_path):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nBody.")
        result = await reconciler.run()
        assert result == (1, 0, 0)
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].title == "A"

    @pytest.mark.asyncio
    async def test_no_changes_skips_embedding(self, reconciler, embed_client, tmp_path):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nBody.")
        await reconciler.run()
        embed_client.embed_batch.reset_mock()
        result = await reconciler.run()
        assert result == (0, 0, 1)
        embed_client.embed_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_edited_body_re_embeds(self, reconciler, tmp_path):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nv1.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nv2.")
        result = await reconciler.run()
        assert result == (1, 0, 0)

    @pytest.mark.asyncio
    async def test_edited_frontmatter_only_re_embeds(self, reconciler, tmp_path, session):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nBody.")
        await reconciler.run()
        _write(tmp_path, "a.md", "---\ntitle: A\ntype: paper\n---\nBody.")
        result = await reconciler.run()
        assert result == (1, 0, 0)
        note = session.scalars(select(Note)).first()
        assert note.type == "paper"

    @pytest.mark.asyncio
    async def test_deletes_removed_file(self, reconciler, tmp_path, session):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nBody.")
        await reconciler.run()
        (tmp_path / "_processed" / "a.md").unlink()
        result = await reconciler.run()
        assert result == (0, 1, 0)
        assert list(session.scalars(select(Note))) == []
        assert list(session.scalars(select(Chunk))) == []

    @pytest.mark.asyncio
    async def test_broken_frontmatter_still_ingests(self, reconciler, tmp_path, session):
        _write(tmp_path, "a.md", "---\ntitle: [unterminated\n---\nBody.")
        result = await reconciler.run()
        assert result == (1, 0, 0)
        note = session.scalars(select(Note)).first()
        # Title falls back to filename stem.
        assert note.title == "a"

    @pytest.mark.asyncio
    async def test_partial_failure_persists_other_notes(
        self, reconciler, embed_client, tmp_path, session
    ):
        _write(tmp_path, "a.md", "---\ntitle: A\n---\nBody A.")
        _write(tmp_path, "b.md", "---\ntitle: B\n---\nBody B.")
        _write(tmp_path, "c.md", "---\ntitle: C\n---\nBody C.")

        call = {"n": 0}

        async def flaky(texts):
            call["n"] += 1
            if call["n"] == 2:
                raise RuntimeError("embed boom")
            return [[0.1] * 1024 for _ in texts]

        embed_client.embed_batch.side_effect = flaky
        with pytest.raises(RuntimeError):
            await reconciler.run()
        titles = sorted(n.title for n in session.scalars(select(Note)))
        assert "B" not in titles
        assert len(titles) == 2

    @pytest.mark.asyncio
    async def test_file_disappears_mid_cycle(self, reconciler, tmp_path):
        _write(tmp_path, "ghost.md", "---\ntitle: G\n---\nx.")
        original = reconciler._read_text  # type: ignore[attr-defined]

        def vanish(path):
            raise FileNotFoundError(path)

        reconciler._read_text = vanish  # type: ignore[attr-defined]
        result = await reconciler.run()
        # File treated as "delete next cycle" — no crash, no upsert.
        assert result[0] == 0
        reconciler._read_text = original  # type: ignore[attr-defined]
```

**Step 2: Run tests, expect failure**

```bash
bb remote test //projects/monolith/knowledge:reconciler_test --config=ci
```

Expected: FAIL.

**Step 3: Implement `reconciler.py`**

```python
"""Vault → knowledge schema reconciler."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol

from knowledge import frontmatter, links
from knowledge.store import KnowledgeStore
from shared.chunker import chunk_markdown

logger = logging.getLogger("monolith.knowledge.reconciler")


class _Embedder(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class Reconciler:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        embed_client: _Embedder,
        vault_root: Path,
    ) -> None:
        self.store = store
        self.embed_client = embed_client
        self.vault_root = Path(vault_root)
        self.processed_root = self.vault_root / "_processed"

    async def run(self) -> tuple[int, int, int]:
        """Returns (upserted, deleted, unchanged)."""
        on_disk = self._walk()
        indexed = self.store.get_indexed()

        to_upsert = [
            path for path, h in on_disk.items() if indexed.get(path) != h
        ]
        to_delete = [path for path in indexed if path not in on_disk]
        unchanged = len(on_disk) - len(to_upsert)

        for path in to_delete:
            logger.info("knowledge: deleting %s", path)
            self.store.delete_note(path)

        upserted = 0
        for path in to_upsert:
            try:
                await self._ingest_one(path, on_disk[path])
            except FileNotFoundError:
                logger.warning("knowledge: file vanished mid-cycle: %s", path)
                continue
            upserted += 1

        logger.info(
            "knowledge: reconciled upserted=%d deleted=%d unchanged=%d",
            upserted, len(to_delete), unchanged,
        )
        return upserted, len(to_delete), unchanged

    def _walk(self) -> dict[str, str]:
        if not self.processed_root.exists():
            return {}
        out: dict[str, str] = {}
        for p in self.processed_root.rglob("*.md"):
            try:
                data = p.read_bytes()
            except (FileNotFoundError, PermissionError):
                continue
            rel = p.relative_to(self.vault_root).as_posix()
            out[rel] = hashlib.sha256(data).hexdigest()
        return out

    def _read_text(self, abs_path: Path) -> str:
        try:
            return abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("knowledge: invalid utf-8, skipping: %s", abs_path)
            raise

    async def _ingest_one(self, rel_path: str, content_hash: str) -> None:
        abs_path = self.vault_root / rel_path
        try:
            raw = self._read_text(abs_path)
        except UnicodeDecodeError:
            return

        meta, body = frontmatter.parse(raw)
        title = meta.title or Path(rel_path).stem
        chunks = chunk_markdown(body)
        if not chunks:
            chunks = [{"index": 0, "section_header": "", "text": body or title}]
        vectors = await self.embed_client.embed_batch([c["text"] for c in chunks])
        wikilinks = links.extract(body)

        self.store.upsert_note(
            path=rel_path,
            content_hash=content_hash,
            title=title,
            metadata=meta,
            chunks=chunks,
            vectors=vectors,
            links=wikilinks,
        )
```

**Step 4: Run tests, expect pass**

```bash
bb remote test //projects/monolith/knowledge:reconciler_test --config=ci
```

Expected: PASS.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/reconciler.py projects/monolith/knowledge/reconciler_test.py projects/monolith/knowledge/BUILD.bazel
git commit -m "feat(knowledge): add vault reconciler"
```

---

### Task 8: Wire up the scheduler job

**Files:**

- Create: `projects/monolith/knowledge/service.py`
- Modify: `projects/monolith/app/main.py:60-65` (add `knowledge_startup` call)
- Modify: `projects/monolith/app/BUILD.bazel` and `projects/monolith/knowledge/BUILD.bazel`

**Step 1: Read the existing `on_startup` convention**

Open `projects/monolith/shared/service.py` and `projects/monolith/home/service.py`. Both expose:

```python
def on_startup(session: Session) -> None: ...
```

…and use `shared.scheduler.register_job` to bind a handler. Match this pattern exactly.

**Step 2: Implement `knowledge/service.py`**

```python
"""Startup hook that registers the knowledge reconcile job."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient
from shared.scheduler import register_job

logger = logging.getLogger("monolith.knowledge.service")

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
_INTERVAL_SECS = 300
_TTL_SECS = 600


async def _handle(session: Session) -> datetime | None:
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    reconciler = Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
        vault_root=vault_root,
    )
    await reconciler.run()
    return None  # let the scheduler use interval_secs


def on_startup(session: Session) -> None:
    register_job(
        session,
        name="knowledge.reconcile",
        interval_secs=_INTERVAL_SECS,
        handler=_handle,
        ttl_secs=_TTL_SECS,
    )
    logger.info("knowledge.reconcile job registered")
```

**Step 3: Wire it into `app/main.py`**

Edit `projects/monolith/app/main.py:60-65` (the lifespan startup block) to add knowledge alongside home and shared:

```python
with Session(get_engine()) as session:
    from home.service import on_startup as home_startup
    from knowledge.service import on_startup as knowledge_startup
    from shared.service import on_startup as shared_startup

    home_startup(session)
    shared_startup(session)
    knowledge_startup(session)
```

**Step 4: Update BUILD files**

Add `knowledge/service.py` to the knowledge target. Add `//projects/monolith/knowledge` to the `app` target's deps. Run `format`.

**Step 5: Smoke-test the wiring**

```bash
bb remote test //projects/monolith/knowledge/... --config=ci
bb remote test //projects/monolith/app/... --config=ci
```

Expected: PASS for everything that previously passed; the scheduler integration is exercised in production at startup, not in unit tests.

**Step 6: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/BUILD.bazel projects/monolith/app/main.py projects/monolith/app/BUILD.bazel
git commit -m "feat(knowledge): register reconcile job at startup"
```

---

### Task 9: Chart bump + verify + PR

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` (`version: 0.24.0` → `0.25.0`)
- Modify: `projects/monolith/deploy/application.yaml` (`targetRevision: 0.24.0` → `0.25.0`)

**Step 1: Bump both files in lockstep**

The `chart-version-bot` automates this in CI but we bump manually so the PR is internally consistent. Per CLAUDE.md "Bumping `Chart.yaml` without `application.yaml`" anti-pattern.

**Step 2: Render the chart locally**

```bash
helm template monolith projects/monolith/chart -f projects/monolith/deploy/values.yaml > /tmp/render.yaml
grep -c "20260408000000_knowledge_schema" /tmp/render.yaml
```

Expected: ≥1 (the migration is in the configmap).

**Step 3: Run the full monolith test target**

```bash
bb remote test //projects/monolith/... --config=ci
```

Expected: all green. If the embedding test move (Task 3) missed a caller, this surfaces it.

**Step 4: Commit and push**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "build(monolith): bump chart to 0.25.0 for knowledge service"
git push -u origin feat/knowledge-service
```

**Step 5: Open the PR**

```bash
gh pr create --title "feat(monolith): add knowledge ingestion service" --body "$(cat <<'EOF'
## Summary

- New `knowledge` schema (notes + chunks + note_links) with frontmatter promoted to filterable columns and a 1024-dim pgvector HNSW index
- New `knowledge/` module reconciles `/vault/_processed/**/*.md` on a 5-min cadence via the existing `scheduler.scheduled_jobs` infrastructure
- Lifts the markdown chunker (from `vault_mcp`) and the embedding client (from `chat`) into a new `shared/` package; chat callers retargeted in the same PR (no compat shim)
- All-or-nothing per-note transactions, lenient frontmatter parsing, content-hash diff for idempotence

Design: `docs/plans/2026-04-07-monolith-knowledge-service-design.md`
Plan: `docs/plans/2026-04-07-monolith-knowledge-service-plan.md`

## Test plan

- [ ] `bb remote test //projects/monolith/... --config=ci` green
- [ ] Migration applies cleanly in the rendered configmap
- [ ] Once deployed: `scheduler.scheduled_jobs` shows `knowledge.reconcile` with a recent `last_run_at`
- [ ] Once deployed: `SELECT count(*) FROM knowledge.notes` reflects `_processed/` content
EOF
)"
```

**Step 6: Watch CI**

```bash
gh pr view --json state,mergeStateStatus
```

Address any format-bot or test failures by iterating with `bb remote test` (do not push speculative commits).

---

## Notes for the executor

- **Never run tests locally.** Use `bb remote test //target --config=ci` for everything.
- **Run `format` after every code change** before committing — it runs gazelle and the standalone formatters.
- **Use the `superpowers:test-driven-development` skill** for every code task: test → fail → minimal impl → pass → commit.
- **Use `superpowers:verification-before-completion`** before claiming a task is done.
- **No backwards-compat shims.** When Task 3 retargets chat callers, delete the old `chat/embedding.py` outright.
- **The `session.scalars(select(col1, col2))` pitfall:** `scalars()` returns only the first column. For tuple results use `session.execute(select(...)).all()`. Task 6's `get_indexed` shows the correct pattern.
- **SQLite test fixture caveats:** `pgvector.sqlalchemy.Vector` already works through the `chat/store_test.py:14-34` fixture. `ARRAY(String)` and `JSON` are natively supported by SQLAlchemy under SQLite. If anything trips, fall back to `Column(JSON)` for the offending list column.
- **Chart version is already 0.24.0.** Task 9 bumps to 0.25.0, not 0.24.1 — feature work warrants a minor bump.

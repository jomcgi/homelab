# Gardener: Claude Code CLI Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Anthropic SDK tool-use loop in the knowledge gardener with a `claude` CLI subprocess, enabling use of the existing Claude OAuth token instead of a pay-per-token API key.

**Architecture:** The `Gardener._ingest_one` method is replaced with a `claude --print` subprocess invocation. Claude uses its native `Read`, `Write`, `Edit`, and `Bash` tools to decompose vault notes and write typed markdown artifacts to `_processed/`. A small `knowledge-search` shell script provides semantic search. The `claude` native binary (~100 MB, no Node required) is added to the monolith container image via a `multiarch_http_file` rule and a new `multiarch_tars` parameter on `py3_image`. The gardener no longer needs an Anthropic client, KnowledgeStore, or EmbeddingClient — file I/O is Claude's job; the reconciler (unchanged) picks up the output.

**Tech Stack:** Python asyncio subprocess, Claude Code CLI (native binary), Bazel `multiarch_http_file`, `multiarch_tars` extension to `py3_image.bzl`, Helm `CLAUDE_CODE_OAUTH_TOKEN` secret injection.

---

## Context

### Current state (on `feat/knowledge-gardener`)

- `projects/monolith/knowledge/gardener.py` — `Gardener` class with `anthropic_client`, `store`, `embed_client` constructor args; `_ingest_one` runs an Anthropic SDK tool-use loop
- `projects/monolith/knowledge/service.py` — `garden_handler` checks `ANTHROPIC_AUTH_TOKEN`, constructs `anthropic.Anthropic(auth_token=...)`, passes it to Gardener
- `projects/monolith/chart/templates/deployment.yaml` — injects `ANTHROPIC_AUTH_TOKEN` from the `litellm-claude-auth` secret
- `bazel/tools/oci/py3_image.bzl` — `py3_image` macro has `tars` (arch-independent) but no `multiarch_tars`
- `bazel/tools/http/multiarch_http_file.bzl` — repo rule to download arch-specific binaries; creates `@name//:tar_amd64` and `@name//:tar_arm64`

### Key architectural insight

`Gardener._handle_create_note` already writes markdown files to `_processed/` rather than directly to the database. The reconciler picks them up on its next tick. This means **all the gardener's tool operations are pure file I/O** — exactly what Claude Code's native tools (`Read`, `Write`, `Edit`) do. The only non-file operation is semantic search, provided via a shell script.

### What the reconciler expects in `_processed/`

Valid markdown with YAML frontmatter:

```yaml
---
id: <slug>
title: <string>
type: atom|fact|active
tags: [optional, list]
edges:
  derives_from: [other-note-id]
---
<markdown body>
```

---

## Task 1: Add `multiarch_tars` to `py3_image.bzl`

**Files:**

- Modify: `bazel/tools/oci/py3_image.bzl`

`py3_image` passes the same `tars` list to both amd64 and arm64 `oci_image` targets. Add a `multiarch_tars` parameter that uses `{base}_amd64` / `{base}_arm64` suffixes (same convention as `apko_image`).

**Step 1: Write a build-level smoke test**

The existing `bb remote test //projects/monolith:image_config_test --config=ci` covers this. No new test file needed.

**Step 2: Change the function signature**

From:

```python
def py3_image(name, binary, main = None, root = "/", layer_groups = {}, env = {}, workdir = None, base = "@python_base", tars = [], bash_symlink = True, repository = None, visibility = ["//bazel/images:__pkg__"], multi_platform = True):
```

To:

```python
def py3_image(name, binary, main = None, root = "/", layer_groups = {}, env = {}, workdir = None, base = "@python_base", tars = [], multiarch_tars = [], bash_symlink = True, repository = None, visibility = ["//bazel/images:__pkg__"], multi_platform = True):
```

**Step 3: Build arch-specific tar lists**

After `extra_tars = list(tars)` and before `if bash_symlink:`, add:

```python
    extra_tars_amd64 = list(extra_tars)
    extra_tars_arm64 = list(extra_tars)
    for tar_base in multiarch_tars:
        extra_tars_amd64.append(tar_base + "_amd64")
        extra_tars_arm64.append(tar_base + "_arm64")
```

**Step 4: Thread into the two `oci_image` calls**

In the `if multi_platform:` block, change both `oci_image` calls:

- AMD64: `tars = py_image_layer(...) + extra_tars_amd64`
- ARM64: `tars = py_image_layer(...) + extra_tars_arm64`

The single-platform path keeps `extra_tars` (no arch distinction needed there).

**Step 5: Commit**

```bash
git add bazel/tools/oci/py3_image.bzl
git commit -m "feat(bazel): add multiarch_tars parameter to py3_image"
```

---

## Task 2: Register `claude` native binary in `MODULE.bazel`

**Files:**

- Modify: `MODULE.bazel`

**Step 1: Find the latest release URLs and hashes**

```bash
# List release assets
curl -s https://api.github.com/repos/anthropics/claude-code/releases/latest \
  | python3 -c "import sys,json; r=json.load(sys.stdin); [print(a['name'], a['browser_download_url']) for a in r['assets']]"
```

Look for assets like `claude-linux-x64` (amd64) and `claude-linux-arm64`.

Download and hash them:

```bash
curl -L -o /tmp/claude-amd64 <amd64_url>
curl -L -o /tmp/claude-arm64 <arm64_url>
sha256sum /tmp/claude-amd64 /tmp/claude-arm64
```

**Step 2: Add the entry near the other `multiarch_http_file` entries (around line 372)**

```python
multiarch_http_file(
    name = "claude_code",
    amd64_url = "<amd64_url>",
    amd64_sha256 = "<amd64_sha256>",
    arm64_url = "<arm64_url>",
    arm64_sha256 = "<arm64_sha256>",
    binary_name = "claude",
)
```

**Step 3: Add `"claude_code"` to the `use_repo` call**

Find the `use_repo(http, ...)` line that already includes `"bb"`. Add `"claude_code"` to that same list. **Forgetting this step causes a confusing build error.**

**Step 4: Verify**

```bash
bb remote build @claude_code//:tar_amd64 --config=ci
```

Expected: downloads binary and creates tar successfully.

**Step 5: Commit**

```bash
git add MODULE.bazel
git commit -m "build(monolith): register claude Code native binary in MODULE.bazel"
```

---

## Task 3: Add `claude` binary to the monolith image

**Files:**

- Modify: `projects/monolith/BUILD` (the `py3_image` call at line ~85)

**Step 1: Add `multiarch_tars` to the `py3_image` call**

```python
py3_image(
    name = "image",
    binary = "//projects/monolith:main",
    env = { ... },          # unchanged
    main = "app/main.py",
    multiarch_tars = ["@claude_code//:tar"],
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/backend",
)
```

**Step 2: Build**

```bash
bb remote build //projects/monolith:image --config=ci
```

**Step 3: Commit**

```bash
git add projects/monolith/BUILD
git commit -m "build(monolith): add claude Code CLI binary to backend image"
```

---

## Task 4: Create `knowledge-search` CLI script and add to image

**Files:**

- Create: `projects/monolith/knowledge/tools/knowledge-search`
- Modify: `projects/monolith/BUILD`

**Step 1: Check if the monolith has a REST search endpoint**

Read `projects/monolith/knowledge/` for a `router.py`. Look for a `/search` or `/notes/search` route that calls `KnowledgeStore.search_notes`. Note the URL path and query parameter name.

**Step 2: Create the script**

If a REST endpoint exists (e.g. `GET /knowledge/search?q=<query>`):

```bash
#!/bin/sh
# knowledge-search: semantic search over the knowledge store.
# Usage: knowledge-search <query string>
# Prints JSON array of matching notes to stdout.
set -e
QUERY="$*"
if [ -z "$QUERY" ]; then
  echo '[]'
  exit 0
fi
ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QUERY")
curl -sf "http://localhost:${MONOLITH_PORT:-8000}/knowledge/search?q=${ENCODED}"
```

If no REST endpoint exists, use the Python version that calls the embedding service and DB directly:

```python
#!/usr/bin/env python3
"""Semantic search for the knowledge gardener.
Usage: knowledge-search <query>
Prints JSON to stdout.
"""
import asyncio, json, os, sys

async def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("[]")
        return
    from shared.embedding import EmbeddingClient
    from knowledge.store import KnowledgeStore
    from sqlmodel import Session, create_engine
    engine = create_engine(os.environ["DATABASE_URL"])
    embed_client = EmbeddingClient()
    embedding = await embed_client.embed(query)
    with Session(engine) as session:
        results = KnowledgeStore(session=session).search_notes(
            query_embedding=embedding, limit=5
        )
    print(json.dumps(results))

asyncio.run(main())
```

Make it executable: `chmod +x projects/monolith/knowledge/tools/knowledge-search`

**Step 3: Add to the image as a tar layer**

In `projects/monolith/BUILD`, add before the `py3_image` call:

```python
tar(
    name = "knowledge_tools_tar",
    srcs = ["knowledge/tools/knowledge-search"],
    mtree = [
        "./usr/local/bin/knowledge-search type=file content=$(execpath knowledge/tools/knowledge-search) mode=0755 uid=0 gid=0",
    ],
)
```

Update `py3_image`:

```python
py3_image(
    name = "image",
    ...
    tars = [":knowledge_tools_tar"],
    multiarch_tars = ["@claude_code//:tar"],
    ...
)
```

**Step 4: Build and commit**

```bash
bb remote build //projects/monolith:image --config=ci
git add projects/monolith/knowledge/tools/ projects/monolith/BUILD
git commit -m "feat(knowledge): add knowledge-search CLI tool to monolith image"
```

---

## Task 5: Rewrite `Gardener._ingest_one` to use claude subprocess

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

### Step 1: Write failing tests

Add to `gardener_test.py`:

```python
class TestIngestOneClaude:
    @pytest.mark.asyncio
    async def test_spawns_claude_with_correct_flags(self, tmp_path):
        """_ingest_one spawns: claude --print --allowedTools Bash,Read,Write,Edit -p <prompt>."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\nsome content")
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock) as mock_exec:
            await Gardener(vault_root=vault)._ingest_one(note)

        args = mock_exec.call_args[0]
        assert args[0] == "claude"
        assert "--print" in args
        assert "--allowedTools" in args
        allowed_idx = list(args).index("--allowedTools")
        allowed_tools = args[allowed_idx + 1]
        assert "Bash" in allowed_tools
        assert "Write" in allowed_tools

    @pytest.mark.asyncio
    async def test_soft_deletes_after_notes_created(self, tmp_path):
        """Raw file is moved to _deleted_with_ttl/ if claude creates notes in _processed/."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")
        processed = vault / "_processed"
        processed.mkdir()

        proc_mock = AsyncMock()
        proc_mock.returncode = 0

        async def fake_communicate():
            (processed / "hello.md").write_text(
                "---\nid: hello\ntitle: Hello\ntype: atom\n---\nbody"
            )
            return b"", b""

        proc_mock.communicate = fake_communicate

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await Gardener(vault_root=vault)._ingest_one(note)

        assert not note.exists()
        deleted = list((vault / "_deleted_with_ttl").rglob("*.md"))
        assert len(deleted) == 1

    @pytest.mark.asyncio
    async def test_leaves_raw_when_no_notes_created(self, tmp_path):
        """Raw file stays if claude exits 0 but writes no notes."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 0
        proc_mock.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            await Gardener(vault_root=vault)._ingest_one(note)

        assert note.exists()

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, tmp_path):
        """RuntimeError is raised when claude exits with non-zero status."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "test.md"
        note.write_text("# Hello\ncontent")

        proc_mock = AsyncMock()
        proc_mock.returncode = 1
        proc_mock.communicate = AsyncMock(return_value=(b"", b"auth error"))

        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with pytest.raises(RuntimeError, match="claude exited 1"):
                await Gardener(vault_root=vault)._ingest_one(note)
```

**Step 2: Run to confirm failure**

```bash
cd projects/monolith
uv run --no-project --with pytest --with pytest-asyncio --with pyyaml \
  python -m pytest knowledge/gardener_test.py::TestIngestOneClaude -v
```

Expected: FAIL (wrong constructor signature or methods missing).

**Step 3: Rewrite `gardener.py`**

**Remove entirely:**

- `_TOOLS` constant
- `_SYSTEM_PROMPT` constant
- `_DEFAULT_MODEL` constant
- `_is_error_result` function
- `_Embedder` Protocol
- The `TYPE_CHECKING` / `KnowledgeStore` import block
- Methods: `_handle_tool`, `_handle_search_notes`, `_handle_get_note`, `_handle_create_note`, `_handle_patch_edges`

**Add prompt template constant** (after `_SLUG_RE`):

```python
_CLAUDE_PROMPT = """\
You are a knowledge gardener. Decompose the raw note below into atomic knowledge artifacts.

Steps:
1. Run `knowledge-search "<topic>"` (Bash) to find related existing notes.
2. Read related notes from {processed_root}/ using the Read tool.
3. Create each atomic note as a new file in {processed_root}/ using the Write tool.
   Allowed types: atom (concept/principle), fact (verifiable claim), active (journal/TODO).
4. Each file must start with YAML frontmatter:
---
id: <slug-of-title>
title: <concise title>
type: atom|fact|active
tags: [optional]
edges:
  derives_from: [source-slug]
---
<markdown body>
5. Patch edges on related existing notes using the Edit tool.
6. Each note covers exactly one concept. Prefer many small notes over one large note.

Title: {title}

{body}
"""

_CLAUDE_TIMEOUT_SECS = 300
```

**Change `Gardener.__init__`:**

```python
def __init__(
    self,
    *,
    vault_root: Path,
    max_files_per_run: int = _DEFAULT_MAX_FILES_PER_RUN,
    claude_bin: str = "claude",
) -> None:
    self.vault_root = Path(vault_root)
    self.max_files_per_run = max_files_per_run
    self.claude_bin = claude_bin
    self.processed_root = self.vault_root / "_processed"
    self.deleted_root = self.vault_root / "_deleted_with_ttl"
```

**Replace `_ingest_one`:**

```python
async def _ingest_one(self, path: Path) -> None:
    """Decompose a single raw note by spawning a claude Code subprocess."""
    import asyncio

    raw = path.read_text(encoding="utf-8")
    meta, body = frontmatter.parse(raw)
    title = meta.title or path.stem

    prompt = _CLAUDE_PROMPT.format(
        processed_root=self.processed_root,
        title=title,
        body=body,
    )

    before = (
        set(self.processed_root.glob("*.md"))
        if self.processed_root.exists()
        else set()
    )

    proc = await asyncio.create_subprocess_exec(
        self.claude_bin,
        "--print",
        "--allowedTools",
        "Bash,Read,Write,Edit",
        "-p",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=_CLAUDE_TIMEOUT_SECS
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"claude exited {proc.returncode}: "
            f"{stderr.decode(errors='replace')[:300]}"
        )

    after = (
        set(self.processed_root.glob("*.md"))
        if self.processed_root.exists()
        else set()
    )
    if not (after - before):
        logger.warning(
            "gardener: claude produced no notes for %s; leaving raw file in place",
            path,
        )
        return

    self._soft_delete(path)
```

**Step 4: Run all gardener tests**

```bash
cd projects/monolith
uv run --no-project --with pytest --with pytest-asyncio --with pyyaml \
  python -m pytest knowledge/gardener_test.py -v
```

Expected: all pass. The existing tests (`TestGardener`, `TestMaxFilesPerRun`, `TestDiscoverRawFiles`, `TestCleanupTtl`) should still pass since `run()`, `_discover_raw_files()`, `_soft_delete()`, and `_cleanup_ttl()` are unchanged.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): rewrite gardener ingest to use claude Code CLI subprocess"
```

---

## Task 6: Simplify `service.py` and update env var

**Files:**

- Modify: `projects/monolith/knowledge/service.py`
- Modify: `projects/monolith/knowledge/service_test.py`
- Modify: `projects/monolith/chart/templates/deployment.yaml`

### Step 1: Write failing tests

Replace `TestGardenHandler` in `service_test.py` with:

```python
class TestGardenHandler:
    @pytest.mark.asyncio
    async def test_skips_when_oauth_token_unset(self, monkeypatch):
        """garden_handler returns None without constructing a Gardener when token absent."""
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        session = MagicMock()
        with patch("knowledge.gardener.Gardener") as mock_gardener:
            result = await garden_handler(session)
        assert result is None
        mock_gardener.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_gardener_when_token_set(self, monkeypatch, tmp_path):
        """garden_handler constructs Gardener(vault_root, max_files_per_run) and awaits run()."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=2, failed=0, ttl_cleaned=1)
        )
        with patch(
            "knowledge.gardener.Gardener", return_value=gardener_instance
        ) as mock_gardener:
            result = await garden_handler(session)
        assert result is None
        mock_gardener.assert_called_once()
        kwargs = mock_gardener.call_args.kwargs
        assert kwargs["vault_root"] == tmp_path
        assert kwargs["max_files_per_run"] == 10
        assert "anthropic_client" not in kwargs
        assert "store" not in kwargs
        assert "embed_client" not in kwargs
        gardener_instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_error_when_all_ingests_failed(
        self, monkeypatch, tmp_path, caplog
    ):
        """When every ingest failed, the completion log is promoted to ERROR."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=3, ttl_cleaned=0)
        )
        with (
            patch("knowledge.gardener.Gardener", return_value=gardener_instance),
            caplog.at_level(logging.ERROR, logger="knowledge.service"),
        ):
            await garden_handler(session)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert "all failed" in error_records[0].message

    @pytest.mark.asyncio
    async def test_honors_max_files_env_override(self, monkeypatch, tmp_path):
        """GARDENER_MAX_FILES_PER_RUN env var overrides the default cap."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ot-test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GARDENER_MAX_FILES_PER_RUN", "25")
        session = MagicMock()
        gardener_instance = MagicMock()
        gardener_instance.run = AsyncMock(
            return_value=GardenStats(ingested=0, failed=0, ttl_cleaned=0)
        )
        with patch(
            "knowledge.gardener.Gardener", return_value=gardener_instance
        ) as mock_gardener:
            await garden_handler(session)
        assert mock_gardener.call_args.kwargs["max_files_per_run"] == 25
```

**Step 2: Run to confirm failure**

```bash
cd projects/monolith
uv run --no-project --with pytest --with pytest-asyncio --with pyyaml \
  python -m pytest knowledge/service_test.py::TestGardenHandler -v
```

**Step 3: Rewrite `garden_handler` in `service.py`**

```python
async def garden_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge vault gardener."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        logger.warning("knowledge.garden: CLAUDE_CODE_OAUTH_TOKEN not set, skipping")
        return None

    from knowledge.gardener import Gardener

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    try:
        max_files = int(os.environ.get("GARDENER_MAX_FILES_PER_RUN", "10"))
    except ValueError:
        logger.warning(
            "knowledge.garden: GARDENER_MAX_FILES_PER_RUN is not an integer, "
            "falling back to default",
        )
        max_files = 10
    gardener = Gardener(
        vault_root=vault_root,
        max_files_per_run=max_files,
    )
    stats = await gardener.run()
    extra = {
        "ingested": stats.ingested,
        "failed": stats.failed,
        "ttl_cleaned": stats.ttl_cleaned,
    }
    if stats.ingested == 0 and stats.failed > 0:
        logger.error("knowledge.garden complete (all failed)", extra=extra)
    else:
        logger.info("knowledge.garden complete", extra=extra)
    return None
```

Note: `KnowledgeStore` and `EmbeddingClient` imports stay — they're used by `reconcile_handler`.

**Step 4: Update the Helm deployment template**

Change `ANTHROPIC_AUTH_TOKEN` to `CLAUDE_CODE_OAUTH_TOKEN`:

```yaml
{{- if .Values.gardener.enabled }}
- name: CLAUDE_CODE_OAUTH_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "monolith.fullname" . }}-gardener
      key: CLAUDE_AUTH_TOKEN
{{- end }}
```

**Step 5: Update the chart values comment**

In `projects/monolith/chart/values.yaml`, update the gardener comment from mentioning an API key to mentioning the OAuth token.

**Step 6: Run all service tests**

```bash
cd projects/monolith
uv run --no-project --with pytest --with pytest-asyncio --with pyyaml \
  python -m pytest knowledge/service_test.py -v
```

Expected: all 11 tests pass.

**Step 7: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py \
        projects/monolith/chart/templates/deployment.yaml projects/monolith/chart/values.yaml
git commit -m "feat(knowledge): switch gardener auth to CLAUDE_CODE_OAUTH_TOKEN"
```

---

## Task 7: Clean up unused deps and bump chart version

**Files:**

- Modify: `projects/monolith/BUILD`
- Modify: `projects/monolith/chart/Chart.yaml`
- Modify: `projects/monolith/deploy/application.yaml`

**Step 1: Check if anthropic SDK is still needed**

```bash
grep -r "import anthropic\|@pip//anthropic" projects/monolith/ --include="*.py" --include="BUILD"
```

If no remaining references, remove `"@pip//anthropic"` from the `monolith_backend` py_library deps in `BUILD` and from any test targets.

**Step 2: Run full test suite**

```bash
bb remote test //projects/monolith/... --config=ci
```

Expected: all pass.

**Step 3: Bump chart version** — `0.26.0` → `0.27.0` in `chart/Chart.yaml` and `deploy/application.yaml`.

**Step 4: Push and update PR**

```bash
git add projects/monolith/BUILD projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "build(monolith): bump chart to 0.27.0 for claude CLI backend"
git push origin feat/knowledge-gardener
gh pr edit 1900 --body "$(cat <<'EOF'
## Summary
- Adds knowledge.garden scheduled job decomposing raw Obsidian vault notes into typed knowledge artifacts using Claude Code CLI
- Uses CLAUDE_CODE_OAUTH_TOKEN from existing litellm-claude-auth 1Password item — same token as goose agents, no separate API key needed
- claude native binary added to monolith image via multiarch_http_file Bazel rule (no Node required)
- knowledge-search CLI script provides semantic search within claude sessions
- Reconciler (unchanged) picks up processed notes from _processed/

## Manual step post-merge
Verify litellm-claude-auth item at vaults/k8s-homelab/items/litellm-claude-auth has a field named exactly CLAUDE_AUTH_TOKEN with the OAuth token. Same field used by goose agents — no new 1Password item needed.

## Known limitations
- Crash-time idempotency: pod restart mid-ingest may process a file twice; reconciler handles via supersedes edges
- API vs data error distinction: all failures log as ERROR; full differentiation deferred to follow-up with alert rule

## Test plan
- [x] TestIngestOneClaude — subprocess flags, soft-delete on success, no-op on empty output, error on non-zero exit
- [x] TestGardenHandler — CLAUDE_CODE_OAUTH_TOKEN guard, Gardener wiring, max_files override, all-failed ERROR promotion
- [x] TestOnStartup — garden + reconcile registration order
- [x] TestReconcileHandler — reconciler unchanged
- [ ] End-to-end: merge, verify litellm-claude-auth field, observe first garden cycle in SigNoz logs
EOF
)"
```

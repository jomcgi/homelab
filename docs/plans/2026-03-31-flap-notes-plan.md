# FLAP Notes Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the monolith dashboard's capture textarea to create `#fleeting` notes in the Obsidian vault via a new REST API endpoint chain.

**Architecture:** The SvelteKit frontend POSTs to the monolith's `/api/notes` endpoint, which proxies to a new `/api/notes` REST endpoint on the vault-mcp Starlette server. Vault-mcp generates the timestamped filename and YAML frontmatter, then calls its existing `write_note()` function which handles file creation and git commit.

**Tech Stack:** Python (FastAPI, Starlette, httpx), SvelteKit, Helm

---

### Task 1: Vault-MCP — REST endpoint for note creation

**Files:**

- Modify: `projects/obsidian_vault/vault_mcp/app/main.py`
- Test: `projects/obsidian_vault/vault_mcp/tests/main_test.py`

**Step 1: Write the failing tests**

Add to `projects/obsidian_vault/vault_mcp/tests/main_test.py`:

```python
class TestCreateNoteAPI:
    """Tests for the POST /api/notes REST endpoint."""

    async def test_creates_fleeting_note(self, tmp_path):
        result = await create_note("Hello world", source="web-ui")
        assert result["path"].startswith("Fleeting/")
        assert result["path"].endswith(".md")
        # Verify file was written with frontmatter
        written = (tmp_path / result["path"]).read_text()
        assert "tags: fleeting" in written
        assert "source: web-ui" in written
        assert "Hello world" in written

    async def test_creates_parent_directory(self, tmp_path):
        result = await create_note("Test note", source="web-ui")
        assert (tmp_path / result["path"]).exists()

    async def test_empty_content_returns_error(self, tmp_path):
        result = await create_note("", source="web-ui")
        assert "error" in result

    async def test_whitespace_only_returns_error(self, tmp_path):
        result = await create_note("   \n  ", source="web-ui")
        assert "error" in result

    async def test_default_source_is_api(self, tmp_path):
        result = await create_note("A note")
        written = (tmp_path / result["path"]).read_text()
        assert "source: api" in written

    async def test_frontmatter_format(self, tmp_path):
        result = await create_note("My thought", source="mcp")
        written = (tmp_path / result["path"]).read_text()
        lines = written.split("\n")
        assert lines[0] == "---"
        assert "up:" in written
        assert "tags: fleeting" in written
        assert "source: mcp" in written
        # Frontmatter closes before content
        second_fence = written.index("---", 4)
        assert "My thought" in written[second_fence:]

    async def test_commits_to_git(self, tmp_path):
        import subprocess
        await create_note("Committed note", source="web-ui")
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "fleeting note from web-ui" in log.stdout
```

The import line to add at the top of the test file alongside the existing imports:

```python
from projects.obsidian_vault.vault_mcp.app.main import (
    # ... existing imports ...
    create_note,
)
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: FAIL — `create_note` does not exist yet.

**Step 3: Implement `create_note` function**

Add to `projects/obsidian_vault/vault_mcp/app/main.py`, after the `restore_note` tool and before `_reconcile_loop`:

```python
from datetime import datetime, timezone


async def create_note(content: str, source: str = "api") -> dict:
    """Create a fleeting note with timestamped filename and YAML frontmatter.

    Args:
        content: Raw note text.
        source: Where the note originated (web-ui, mcp, api).

    Returns dict with 'path' on success or 'error' on failure.
    """
    if not content or not content.strip():
        return {"error": "content is required"}

    now = datetime.now(timezone.utc)
    filename = f"Fleeting/{now.strftime('%Y-%m-%d %H%M')}.md"
    body = f"---\nup:\ntags: fleeting\nsource: {source}\n---\n\n{content.strip()}\n"

    return await write_note(path=filename, content=body, reason=f"fleeting note from {source}")
```

Then add the `/api/notes` HTTP route. In the `main()` function, after the `/healthz` route is added:

```python
    async def api_create_note(request):
        from starlette.responses import JSONResponse

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)

        content = body.get("content", "")
        source = body.get("source", "api")
        result = await create_note(content, source=source)

        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result, status_code=201)

    app.add_route("/api/notes", api_create_note, methods=["POST"])
```

**Step 4: Run tests to verify they pass**

Run: `bazel test //projects/obsidian_vault/vault_mcp/tests:main_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/obsidian_vault/vault_mcp/app/main.py projects/obsidian_vault/vault_mcp/tests/main_test.py
git commit -m "feat(obsidian): add POST /api/notes REST endpoint for fleeting note creation"
```

---

### Task 2: Vault-MCP — Chart version bump

**Files:**

- Modify: `projects/obsidian_vault/chart/Chart.yaml` (version `0.5.16` → `0.5.17`)
- Modify: `projects/obsidian_vault/deploy/application.yaml` (targetRevision `0.5.16` → `0.5.17`)

**Step 1: Bump chart version**

In `projects/obsidian_vault/chart/Chart.yaml`, change:

```yaml
version: 0.5.17
```

**Step 2: Update application targetRevision**

In `projects/obsidian_vault/deploy/application.yaml`, change:

```yaml
targetRevision: 0.5.17
```

**Step 3: Commit**

```bash
git add projects/obsidian_vault/chart/Chart.yaml projects/obsidian_vault/deploy/application.yaml
git commit -m "chore(obsidian): bump chart to 0.5.17 for notes API endpoint"
```

---

### Task 3: Monolith — Notes module (service + router + tests)

**Files:**

- Create: `projects/monolith/notes/__init__.py`
- Create: `projects/monolith/notes/service.py`
- Create: `projects/monolith/notes/router.py`
- Create: `projects/monolith/notes/service_test.py`
- Create: `projects/monolith/notes/router_test.py`
- Modify: `projects/monolith/app/main.py`

**Step 1: Write the service test**

Create `projects/monolith/notes/service_test.py`:

```python
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from notes.service import create_fleeting_note, VAULT_API_URL


@pytest.fixture(autouse=True)
def _set_vault_url(monkeypatch):
    monkeypatch.setenv("VAULT_API_URL", "http://vault-mcp:8000")


class TestCreateFleetingNote:
    async def test_posts_to_vault_api(self):
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"path": "Fleeting/2026-03-31 1423.md"}
        mock_response.raise_for_status = AsyncMock()

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            result = await create_fleeting_note("My thought")

        MockClient.return_value.post.assert_called_once_with(
            "http://vault-mcp:8000/api/notes",
            json={"content": "My thought", "source": "web-ui"},
        )
        assert result == {"path": "Fleeting/2026-03-31 1423.md"}

    async def test_raises_on_vault_error(self):
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_response
        )

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await create_fleeting_note("test")
```

**Step 2: Write the service**

Create `projects/monolith/notes/__init__.py` (empty file).

Create `projects/monolith/notes/service.py`:

```python
"""Notes service — proxies fleeting note creation to vault-mcp."""

import os

import httpx

VAULT_API_URL = os.environ.get("VAULT_API_URL", "")


async def create_fleeting_note(content: str) -> dict:
    """Send a fleeting note to the vault-mcp API."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(
            f"{VAULT_API_URL}/api/notes",
            json={"content": content, "source": "web-ui"},
        )
        resp.raise_for_status()
        return resp.json()
```

**Step 3: Run service tests**

Run: `bazel test //projects/monolith/notes:service_test`
Expected: PASS

**Step 4: Write the router test**

Create `projects/monolith/notes/router_test.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(name="client")
def client_fixture():
    return TestClient(app, raise_server_exceptions=False)


def test_create_note_success(client):
    with patch(
        "notes.router.create_fleeting_note",
        new_callable=AsyncMock,
        return_value={"path": "Fleeting/2026-03-31 1423.md"},
    ):
        response = client.post(
            "/api/notes", json={"content": "Quick thought"}
        )
    assert response.status_code == 201
    assert response.json()["path"] == "Fleeting/2026-03-31 1423.md"


def test_create_note_empty_content(client):
    response = client.post("/api/notes", json={"content": ""})
    assert response.status_code == 400


def test_create_note_missing_content(client):
    response = client.post("/api/notes", json={})
    assert response.status_code == 422


def test_create_note_vault_error(client):
    with patch(
        "notes.router.create_fleeting_note",
        new_callable=AsyncMock,
        side_effect=Exception("vault down"),
    ):
        response = client.post(
            "/api/notes", json={"content": "A thought"}
        )
    assert response.status_code == 502
```

**Step 5: Write the router**

Create `projects/monolith/notes/router.py`:

```python
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import create_fleeting_note

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteCreate(BaseModel):
    content: str


@router.post("", status_code=201)
async def post_note(data: NoteCreate) -> dict:
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    try:
        return await create_fleeting_note(data.content)
    except Exception:
        logger.exception("Failed to create note in vault")
        raise HTTPException(status_code=502, detail="vault unavailable")
```

**Step 6: Register router in main.py**

In `projects/monolith/app/main.py`, add import and include:

```python
from notes.router import router as notes_router
```

And after the existing `app.include_router(schedule_router)` line:

```python
app.include_router(notes_router)
```

**Step 7: Run router tests**

Run: `bazel test //projects/monolith/notes:router_test`
Expected: PASS

**Step 8: Commit**

```bash
git add projects/monolith/notes/ projects/monolith/app/main.py
git commit -m "feat(monolith): add notes module with POST /api/notes proxy to vault-mcp"
```

---

### Task 4: Monolith — Infrastructure wiring

**Files:**

- Modify: `projects/monolith/chart/templates/deployment.yaml`
- Modify: `projects/monolith/chart/values.yaml`
- Modify: `projects/monolith/deploy/values.yaml`
- Modify: `projects/monolith/chart/Chart.yaml` (version `0.7.0` → `0.7.1`)
- Modify: `projects/monolith/deploy/application.yaml` (targetRevision `0.7.0` → `0.7.1`)

**Step 1: Add VAULT_API_URL to chart values**

In `projects/monolith/chart/values.yaml`, add under the `backend:` section:

```yaml
backend:
  # ... existing fields ...
  vaultApiUrl: ""
```

**Step 2: Add env var to deployment template**

In `projects/monolith/chart/templates/deployment.yaml`, add after the `ICAL_FEED_URL` env block (after the `{{- end }}` that closes the `onepassword.enabled` conditional):

```yaml
            {{- if .Values.backend.vaultApiUrl }}
            - name: VAULT_API_URL
              value: {{ .Values.backend.vaultApiUrl | quote }}
            {{- end }}
```

**Step 3: Set the URL in deploy values**

In `projects/monolith/deploy/values.yaml`, add:

```yaml
backend:
  vaultApiUrl: "http://obsidian-vault.obsidian.svc.cluster.local:8000"
```

**Step 4: Bump chart version**

In `projects/monolith/chart/Chart.yaml`, change `version: 0.7.0` to `version: 0.7.1`.

In `projects/monolith/deploy/application.yaml`, change `targetRevision: 0.7.0` to `targetRevision: 0.7.1`.

**Step 5: Verify Helm renders correctly**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml`

Check that the deployment contains `VAULT_API_URL` env var with the correct value.

**Step 6: Commit**

```bash
git add projects/monolith/chart/ projects/monolith/deploy/
git commit -m "feat(monolith): wire VAULT_API_URL env var for notes API"
```

---

### Task 5: Frontend — Wire capture to POST /api/notes

**Files:**

- Modify: `projects/monolith/frontend/src/routes/+page.svelte`

**Step 1: Update `submitCapture()` to call the API**

In `projects/monolith/frontend/src/routes/+page.svelte`, replace the `submitCapture` function (lines 13-21):

```javascript
let error = $state(false);

async function submitCapture() {
  if (!note.trim()) return;
  try {
    const res = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: note }),
    });
    if (!res.ok) throw new Error();
    sent = true;
    setTimeout(() => {
      note = "";
      sent = false;
      captureRef?.focus();
    }, 500);
  } catch {
    error = true;
    setTimeout(() => {
      error = false;
      captureRef?.focus();
    }, 2000);
  }
}
```

**Step 2: Update the hint text to show error state**

In the template, update the capture-hint span (around line 169):

```svelte
      <span class="capture-hint" class:capture-hint--error={error}>
        {#if error}
          failed
        {:else if sent}
          sent
        {:else if note.trim()}
          ⌘ enter
        {:else}
          &nbsp;
        {/if}
      </span>
```

**Step 3: Add error style**

In the `<style>` section, add after `.capture-hint`:

```css
.capture-hint--error {
  color: var(--danger);
}
```

**Step 4: Commit**

```bash
git add projects/monolith/frontend/src/routes/+page.svelte
git commit -m "feat(monolith): wire capture textarea to POST /api/notes"
```

---

### Task 6: Verify end-to-end with helm template

**Step 1: Run format**

Run: `format`

This ensures BUILD files are up-to-date for the new `notes/` module.

**Step 2: Render both charts**

Run:

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml
helm template obsidian-vault projects/obsidian_vault/chart/ -f projects/obsidian_vault/deploy/values.yaml
```

Verify:

- Monolith deployment has `VAULT_API_URL` env var
- No template errors

**Step 3: Commit any format changes**

```bash
git add -A
git commit -m "style: auto-format"
```

**Step 4: Push and create PR**

```bash
git push -u origin feat/flap-notes
gh pr create --title "feat: wire capture UI to create fleeting notes in Obsidian vault" --body "$(cat <<'EOF'
## Summary
- Add `POST /api/notes` REST endpoint to vault-mcp for creating fleeting notes with YAML frontmatter
- Add notes module to monolith (router + service) that proxies to vault-mcp
- Wire the dashboard capture textarea to call the new endpoint on ⌘ Enter
- Add VAULT_API_URL env var wiring through Helm charts

## Design
See `docs/plans/2026-03-31-flap-notes-design.md`

## Test plan
- [ ] Vault-mcp tests pass (create_note function + API endpoint)
- [ ] Monolith notes service tests pass (httpx mock)
- [ ] Monolith notes router tests pass (FastAPI TestClient)
- [ ] Helm templates render with VAULT_API_URL env var
- [ ] CI passes (format + bazel test)
- [ ] After deploy: type text in capture box, ⌘ Enter, verify note appears in Obsidian vault under Fleeting/

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

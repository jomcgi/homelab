#!/usr/bin/env python3
"""
Bosun — FastAPI backend bridging the web UI to Claude Code via Agent SDK.

Uses the Claude Agent SDK (`claude-agent-sdk`) for typed async streaming,
session management, and tool handling. Forwards events to the browser over WebSocket.

Usage:
    pip install fastapi "uvicorn[standard]" claude-agent-sdk
    python server.py [--port 8420] [--workdir /path/to/project]

Or with Vite dev server (for hot reload):
    npm run dev    # runs both backend + Vite frontend
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import struct
import sys
import time
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    sys.exit("Install dependencies: pip install fastapi 'uvicorn[standard]'")

try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        SystemMessage,
        AssistantMessage,
        UserMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
    from claude_agent_sdk.types import StreamEvent

    HAS_SDK = True
except ImportError:
    HAS_SDK = False

# Optional Gemini TTS
try:
    from google import genai
    from google.genai import types

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bosun")

# ── Config ──────────────────────────────────────────────────────────────────

# Unset CLAUDECODE to allow nested Claude sessions via the SDK.
# When this server runs inside a Claude Code session, the CLI sets CLAUDECODE
# which prevents launching child sessions. Clearing it here is safe because
# the server is an independent process that intentionally spawns Claude sessions.
os.environ.pop("CLAUDECODE", None)

# Resolve the system Claude CLI path (not the SDK's bundled version, which lacks auth).
# Check common locations since npm/sh may not have the full PATH from fish/zsh.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "")
if not CLAUDE_BIN:
    for candidate in ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            CLAUDE_BIN = candidate
            break
if not CLAUDE_BIN:
    import shutil

    CLAUDE_BIN = shutil.which("claude") or ""
CLAUDE_CLI_PATH = CLAUDE_BIN or None
if CLAUDE_CLI_PATH:
    log.info("Using system Claude CLI: %s", CLAUDE_CLI_PATH)
else:
    log.warning("System claude not found — SDK will use bundled CLI (may lack auth)")
GOLDEN_PATH = os.environ.get("BOSUN_GOLDEN_PATH", "")
SESSIONS_PATH = os.environ.get("BOSUN_SESSIONS_PATH", "")
if GOLDEN_PATH and os.path.isdir(os.path.join(GOLDEN_PATH, ".git")):
    log.info("Golden clone: %s, sessions: %s", GOLDEN_PATH, SESSIONS_PATH)
else:
    GOLDEN_PATH = ""  # Disable worktree isolation
    log.info("No golden clone — sessions share the default workdir")

RECORD_FIXTURES_DIR = os.environ.get("BOSUN_RECORD_FIXTURES", "")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    # Try fish shell universal variables as fallback
    try:
        GOOGLE_API_KEY = subprocess.check_output(
            ["fish", "-c", "echo $GOOGLE_API_KEY"], text=True
        ).strip()
        if GOOGLE_API_KEY:
            log.info("Loaded GOOGLE_API_KEY from fish shell")
    except Exception:
        pass

# Tools that are auto-approved (no user prompt needed)
AUTO_APPROVED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "Bash",
    "Edit",
    "Write",
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "SendMessage",
    "Teammate",  # Enable swarm/team tools
]

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── SQLite persistence ─────────────────────────────────────────────────────

DB_PATH = Path.home() / ".claude" / "bosun.db"


def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            slot TEXT NOT NULL DEFAULT '1',
            type TEXT NOT NULL,
            label TEXT,
            data TEXT,
            mime_type TEXT,
            meta TEXT,
            created_at REAL DEFAULT (unixepoch('subsec')),
            UNIQUE(session_id, msg_id, slot)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at REAL DEFAULT (unixepoch('subsec')),
            UNIQUE(session_id, msg_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS prs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            repo TEXT NOT NULL,
            title TEXT,
            url TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'open',
            created_at REAL DEFAULT (unixepoch('subsec')),
            updated_at REAL DEFAULT (unixepoch('subsec')),
            UNIQUE(session_id, pr_number, repo)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_art_session ON artifacts(session_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sum_session ON summaries(session_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_prs_session ON prs(session_id)")
    db.commit()
    db.close()


_init_db()


def _get_db():
    """Get a SQLite connection (lightweight with WAL mode)."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def _save_artifact(session_id: str, msg_id: str, slot: str, artifact: dict):
    """Upsert an artifact row."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO artifacts (session_id, msg_id, slot, type, label, data, mime_type, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, msg_id, slot) DO UPDATE SET
                 type=excluded.type, label=excluded.label, data=excluded.data,
                 mime_type=excluded.mime_type, meta=excluded.meta""",
            (
                session_id,
                msg_id,
                slot,
                artifact.get("type", ""),
                artifact.get("label", ""),
                artifact.get("data", ""),
                artifact.get("mimeType", ""),
                json.dumps(artifact.get("meta")) if artifact.get("meta") else None,
            ),
        )
        db.commit()
    except Exception as e:
        log.warning("Failed to save artifact: %s", e)
    finally:
        db.close()


def _save_summary(session_id: str, msg_id: str, text: str):
    """Upsert a summary row."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO summaries (session_id, msg_id, text)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, msg_id) DO UPDATE SET text=excluded.text""",
            (session_id, msg_id, text),
        )
        db.commit()
    except Exception as e:
        log.warning("Failed to save summary: %s", e)
    finally:
        db.close()


_PR_URL_RE = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")


def _upsert_pr(
    session_id: str,
    pr_number: int,
    repo: str,
    title: str,
    url: str,
    state: str = "open",
) -> dict:
    """Upsert a PR row and return the PR dict."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO prs (session_id, pr_number, repo, title, url, state)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, pr_number, repo) DO UPDATE SET
                 title=excluded.title, url=excluded.url, state=excluded.state,
                 updated_at=unixepoch('subsec')""",
            (session_id, pr_number, repo, title, url, state),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM prs WHERE session_id = ? AND pr_number = ? AND repo = ?",
            (session_id, pr_number, repo),
        ).fetchone()
        return dict(row) if row else {}
    except Exception as e:
        log.warning("Failed to upsert PR: %s", e)
        return {}
    finally:
        db.close()


async def _detect_prs_in_output(text: str, session_id: str | None, ws: WebSocket):
    """Scan tool output for GitHub PR URLs and track them."""
    if not session_id or not text:
        return
    for match in _PR_URL_RE.finditer(text):
        repo, pr_num_str = match.group(1), match.group(2)
        pr_number = int(pr_num_str)
        url = match.group(0)
        # Fetch PR metadata via gh CLI
        title, state = "", "open"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "gh",
                    "pr",
                    "view",
                    pr_num_str,
                    "--repo",
                    repo,
                    "--json",
                    "title,state,url",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                title = data.get("title", "")
                state = data.get("state", "OPEN").lower()
                url = data.get("url", url)
        except Exception as e:
            log.warning("Failed to fetch PR metadata: %s", e)

        pr_dict = _upsert_pr(session_id, pr_number, repo, title, url, state)
        if pr_dict:
            try:
                await ws.send_json({"type": "pr_detected", "pr": pr_dict})
            except Exception:
                pass


async def _poll_prs(ws: WebSocket, session_id: str):
    """Poll open PRs for state changes every 30s."""
    while True:
        await asyncio.sleep(30)
        db = _get_db()
        try:
            open_prs = db.execute(
                "SELECT * FROM prs WHERE session_id = ? AND state = 'open'",
                (session_id,),
            ).fetchall()
            changed = False
            for pr in open_prs:
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "gh",
                            "pr",
                            "view",
                            str(pr["pr_number"]),
                            "--repo",
                            pr["repo"],
                            "--json",
                            "state,title",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        new_state = data["state"].lower()
                        if new_state != pr["state"]:
                            db.execute(
                                "UPDATE prs SET state = ?, title = ?, updated_at = unixepoch('subsec') WHERE id = ?",
                                (new_state, data.get("title", pr["title"]), pr["id"]),
                            )
                            db.commit()
                            changed = True
                except Exception as e:
                    log.warning("PR poll error for #%s: %s", pr["pr_number"], e)

            # Send full PR list to frontend on any change or periodically
            all_prs = db.execute(
                "SELECT * FROM prs WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
            if all_prs:
                await ws.send_json(
                    {
                        "type": "prs_update",
                        "prs": [dict(r) for r in all_prs],
                    }
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("PR poll error: %s", e)
            await asyncio.sleep(30)
        finally:
            db.close()


if not HAS_SDK:
    log.warning("claude-agent-sdk not installed — run: pip install claude-agent-sdk")

# ── Per-session clone isolation ─────────────────────────────────────────────


def _create_session_workdir(base_workdir: str, session_name: str | None = None) -> str:
    """Create an isolated working directory for a new session.

    Uses ``git clone --local`` from the golden clone so each session gets an
    independent ``.git/`` directory.  Object files are hardlinked (fast,
    space-efficient) and git's content-addressed store is safe to read
    concurrently — unlike ``cp -a`` or ``git worktree add``, this does not
    race with the git-sync loop that runs fetch+reset every 60 s.

    Args:
        base_workdir: The default working directory to fall back to.
        session_name: Optional stable name for the session directory.
            If not provided, uses a timestamp-based name.
    """
    if not GOLDEN_PATH or not SESSIONS_PATH:
        return base_workdir

    name = session_name or f"s-{int(time.time() * 1000)}"
    session_dir = os.path.join(SESSIONS_PATH, name)
    try:
        os.makedirs(SESSIONS_PATH, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--local", GOLDEN_PATH, session_dir],
            check=True,
            capture_output=True,
            text=True,
        )
        branch = f"session/{name}"
        subprocess.run(
            ["git", "-C", session_dir, "checkout", "-b", branch],
            check=True,
            capture_output=True,
            text=True,
        )
        log.info("Created session clone: %s (branch: %s)", session_dir, branch)
        return session_dir
    except subprocess.CalledProcessError as e:
        log.warning(
            "Failed to create session clone: %s — stderr: %s — using default",
            e,
            e.stderr,
        )
        return base_workdir
    except Exception as e:
        log.warning("Failed to create session clone: %s — using default", e)
        return base_workdir


SESSION_TTL_DAYS = int(os.environ.get("BOSUN_SESSION_TTL_DAYS", "7"))


def _touch_session_workdir(workdir: str):
    """Update the mtime of a session worktree to track last activity."""
    if not SESSIONS_PATH or not workdir.startswith(SESSIONS_PATH):
        return
    try:
        os.utime(workdir, None)  # Sets mtime to now
    except OSError:
        pass


def _cleanup_session_workdir(workdir: str):
    """Remove a session clone directory."""
    try:
        shutil.rmtree(workdir, ignore_errors=True)
        log.info("Cleaned up session clone: %s", workdir)
    except Exception as e:
        log.warning("Failed to clean up session clone %s: %s", workdir, e)


def _prune_stale_sessions():
    """Remove session clones with no activity in SESSION_TTL_DAYS.

    Called on startup and periodically. Uses directory mtime to determine
    last activity — each SDK query touches the session dir.
    """
    if not SESSIONS_PATH or not os.path.isdir(SESSIONS_PATH):
        return

    cutoff = time.time() - (SESSION_TTL_DAYS * 86400)
    pruned = 0
    for entry in os.listdir(SESSIONS_PATH):
        path = os.path.join(SESSIONS_PATH, entry)
        if not os.path.isdir(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
        if mtime < cutoff:
            _cleanup_session_workdir(path)
            pruned += 1

    if pruned:
        log.info("Pruned %d stale session clones (TTL: %dd)", pruned, SESSION_TTL_DAYS)
    else:
        log.info("Session prune: nothing to clean up")


# ── Fixture recording (for integration tests) ──────────────────────────────


def _sdk_event_to_dict(msg) -> dict:
    """Convert an SDK message object to a JSON-serialisable dict for fixture recording."""
    if isinstance(msg, SystemMessage):
        return {"kind": "system_init", "data": msg.data}

    if isinstance(msg, StreamEvent):
        return {
            "kind": "stream_event",
            "uuid": msg.uuid,
            "session_id": msg.session_id,
            "event": msg.event,
            "parent_tool_use_id": msg.parent_tool_use_id,
        }

    if isinstance(msg, AssistantMessage):
        blocks = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
            elif isinstance(block, ToolResultBlock):
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": getattr(block, "is_error", False),
                    }
                )
            else:
                blocks.append({"type": type(block).__name__})
        return {
            "kind": "assistant",
            "content": blocks,
            "model": getattr(msg, "model", None),
            "parent_tool_use_id": msg.parent_tool_use_id,
        }

    if isinstance(msg, ResultMessage):
        return {
            "kind": "result",
            "subtype": msg.subtype,
            "session_id": msg.session_id,
            "duration_ms": msg.duration_ms,
            "total_cost_usd": msg.total_cost_usd,
            "num_turns": msg.num_turns,
            "result": msg.result,
            "is_error": msg.is_error,
        }

    if isinstance(msg, UserMessage):
        return {"kind": "user", "tool_use_result": msg.tool_use_result}

    return {"kind": "unknown", "type": type(msg).__name__}


def _record_event(msg, session_name: str) -> None:
    """Append an SDK event to the fixture file for the given session.

    Only active when RECORD_FIXTURES_DIR is set (checked once at module load).
    Uses a simple read-modify-write on a JSON array file per session.
    """
    if not RECORD_FIXTURES_DIR:
        return

    try:
        fixtures_dir = Path(RECORD_FIXTURES_DIR)
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        filepath = fixtures_dir / f"{session_name}.json"

        events: list = []
        if filepath.exists():
            try:
                events = json.loads(filepath.read_text())
            except (json.JSONDecodeError, OSError):
                events = []

        events.append(_sdk_event_to_dict(msg))
        filepath.write_text(json.dumps(events, indent=2, default=str))
        log.debug(
            "Recorded fixture event #%d for session %s", len(events), session_name
        )
    except Exception as e:
        log.debug("Fixture recording failed: %s", e)


# ── Claude Agent SDK session manager ────────────────────────────────────────


class ClaudeSession:
    """Manages a Claude Agent SDK session and streams results to a WebSocket."""

    def __init__(self, workdir: str):
        import uuid

        self._session_name = str(uuid.uuid4())[:8]
        self.workdir = _create_session_workdir(workdir, session_name=self._session_name)
        self.session_id: str | None = None
        self._cancel_event = asyncio.Event()
        # Preserved across retry attempts for fallback result
        self._last_run_text: str = ""
        self._last_tool_summaries: list[str] = []
        # Cross-reconnect dedup: prevent replaying events the frontend
        # already has when include_partial_messages=True replays history.
        self._emitted_tool_ids: set[str] = set()
        self._emitted_text: set[str] = set()

    async def run(self, prompt: str, ws: WebSocket):
        """Run a query via the Agent SDK and stream events to the WebSocket.

        The SDK's async iterator can terminate mid-run when it encounters
        unknown message types (e.g. rate_limit_event).  The subprocess
        keeps running, so we reconnect via ``resume`` until we receive a
        proper ``ResultMessage``.

        We track *consecutive empty reconnects* (reconnects that yield no
        events at all) to detect a truly dead session.  As long as each
        reconnect produces output, the loop continues indefinitely — a
        30-minute swarm task with periodic rate_limit_event disconnects
        will reconnect hundreds of times and that's fine.
        """
        MAX_SILENT_RECONNECTS = 5  # give up after N reconnects with zero events
        RECONNECT_DELAY = 2  # seconds between reconnects
        start = time.monotonic()
        attempt = 0
        silent_streak = 0  # consecutive reconnects that yielded nothing

        while silent_streak < MAX_SILENT_RECONNECTS:
            attempt += 1
            got_result, had_output, msg_count = await self._run_once(
                prompt, ws, attempt
            )
            if got_result:
                return  # Got a proper ResultMessage — truly done
            if self._cancel_event.is_set():
                return  # User cancelled — don't reconnect

            # Track consecutive silent reconnects.  Use msg_count (not
            # had_output) because the subprocess may be alive but idle
            # (thinking, running a long tool, waiting on subagents) —
            # it still emits at least a SystemMessage init on connect.
            if msg_count > 0:
                silent_streak = 0
            else:
                silent_streak += 1

            if silent_streak >= MAX_SILENT_RECONNECTS:
                break

            log.info(
                "Reconnecting to session (attempt %d, elapsed %.0fs, "
                "msgs=%d, silent_streak=%d)",
                attempt,
                time.monotonic() - start,
                msg_count,
                silent_streak,
            )
            await asyncio.sleep(RECONNECT_DELAY)

        # Session appears dead — send fallback from accumulated state
        elapsed = time.monotonic() - start
        if self._last_run_text.strip() or self._last_tool_summaries:
            log.warning(
                "Session ended after %.0fs (%d reconnects, %d silent)"
                " — sending fallback (text_len=%d)",
                elapsed,
                attempt,
                silent_streak,
                len(self._last_run_text.strip()),
            )
            fallback_payload = {
                "type": "result",
                "session_id": self.session_id,
                "full_text": self._last_run_text.strip(),
            }
            if self._last_tool_summaries:
                fallback_payload["tool_summaries"] = self._last_tool_summaries
            await ws.send_json(fallback_payload)
        else:
            log.warning(
                "Session produced no output after %.0fs (%d attempts)",
                elapsed,
                attempt,
            )
            await ws.send_json(
                {
                    "type": "error",
                    "message": "Claude produced no response."
                    " This may be due to rate limiting — try again shortly.",
                }
            )

    async def _run_once(self, prompt: str, ws: WebSocket, attempt: int = 1):
        """Execute a single SDK query attempt.

        Returns (got_result, had_output, msg_count):
        - got_result: True if a ResultMessage was received (session done)
        - had_output: True if text or tool summaries were accumulated
        - msg_count: total messages yielded by the iterator (liveness signal)
        """
        self._cancel_event.clear()

        options = ClaudeAgentOptions(
            cwd=self.workdir,
            # Use the built-in Claude Code system prompt (preset avoids the SDK
            # passing --system-prompt "" which clears it).
            system_prompt={"type": "preset", "preset": "claude_code"},
            allowed_tools=AUTO_APPROVED_TOOLS,
            permission_mode="acceptEdits",
            include_partial_messages=True,
            setting_sources=["project"],
            cli_path=CLAUDE_CLI_PATH or None,
            stderr=lambda line: log.info("claude stderr: %s", line.rstrip()),
        )
        if self.session_id:
            options.resume = self.session_id

        log.info(
            "SDK query (attempt %d): %s... (session=%s)",
            attempt,
            prompt[:60],
            self.session_id or "new",
        )
        _touch_session_workdir(self.workdir)

        text_buf = ""
        full_run_text = ""
        streaming_text = False
        streaming_captured: set[str] = (
            set()
        )  # Text already captured from streaming path
        artifact_counter = 0  # Counter for generating unique msg_ids for artifacts
        tool_summaries = []  # Human-readable tool call summaries for TTS context
        speculative_summary_task: asyncio.Task | None = None  # Background summarization

        got_result = False
        msg_count = 0  # total messages from iterator (liveness signal)

        try:
            msg_iter = query(prompt=prompt, options=options).__aiter__()
            while True:
                try:
                    msg = await msg_iter.__anext__()
                except StopAsyncIteration:
                    log.info(
                        "SDK iteration ended (StopAsyncIteration, msgs=%d)", msg_count
                    )
                    break
                except Exception as iter_err:
                    if "Unknown message type" in str(iter_err):
                        log.info(
                            "SDK: skipping %s: %s", type(iter_err).__name__, iter_err
                        )
                        continue
                    raise

                msg_count += 1
                _record_event(msg, self._session_name)
                log.debug("SDK msg: %s", type(msg).__name__)

                # Check for cancellation
                if self._cancel_event.is_set():
                    log.info("Query cancelled by user")
                    break

                # ── System messages (session init, etc.) ──────────
                if isinstance(msg, SystemMessage):
                    if msg.subtype == "init":
                        self.session_id = msg.data.get("session_id")
                        await ws.send_json(
                            {
                                "type": "session_init",
                                "session_id": self.session_id,
                            }
                        )
                    else:
                        log.info(
                            "SDK SystemMessage subtype=%s data=%s",
                            msg.subtype,
                            msg.data,
                        )
                    continue

                # ── Streaming deltas (partial text from API) ──────
                if isinstance(msg, StreamEvent):
                    ev = msg.event
                    ev_type = ev.get("type", "")

                    if ev_type == "content_block_start":
                        cb = ev.get("content_block", {})
                        if cb.get("type") == "text" and not streaming_text:
                            await ws.send_json({"type": "assistant_start"})
                            streaming_text = True
                            text_buf = ""
                        elif cb.get("type") == "tool_use":
                            tool_id = cb.get("id", "")
                            # Skip Task tools — AssistantMessage handler
                            # sends them with full input/description.
                            # Also skip already-emitted IDs (reconnect replay).
                            if (
                                cb.get("name") != "Task"
                                and tool_id
                                and tool_id not in self._emitted_tool_ids
                            ):
                                self._emitted_tool_ids.add(tool_id)
                                await ws.send_json(
                                    {
                                        "type": "tool_use",
                                        "name": cb.get("name", ""),
                                        "tool_use_id": tool_id,
                                        "summary": f"Using {cb.get('name', '')}",
                                        "parent_tool_use_id": msg.parent_tool_use_id,
                                    }
                                )

                    elif ev_type == "content_block_delta":
                        delta = ev.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            text_buf += chunk
                            await ws.send_json(
                                {
                                    "type": "assistant_text",
                                    "content": chunk,
                                }
                            )

                    elif ev_type == "message_delta":
                        usage = ev.get("usage", {})
                        if usage:
                            await ws.send_json(
                                {
                                    "type": "usage_update",
                                    "input_tokens": usage.get("input_tokens", 0),
                                    "output_tokens": usage.get("output_tokens", 0),
                                }
                            )

                    elif ev_type == "message_stop":
                        if streaming_text:
                            # Deduplicate text across reconnects — the SDK
                            # replays in-flight messages on resume.
                            if text_buf in self._emitted_text:
                                streaming_text = False
                                text_buf = ""
                            else:
                                self._emitted_text.add(text_buf)
                                full_run_text += text_buf + "\n"
                                streaming_captured.add(text_buf)
                                await ws.send_json(
                                    {
                                        "type": "assistant_done",
                                        "full_text": text_buf,
                                    }
                                )
                                # Scan for mermaid blocks in the completed text
                                for mi, mblock in enumerate(
                                    _extract_mermaid_blocks(text_buf)
                                ):
                                    await ws.send_json(
                                        {
                                            "type": "mermaid_artifact",
                                            "code": mblock["code"],
                                            "label": mblock["label"],
                                        }
                                    )
                                    # Auto-save mermaid artifact
                                    if self.session_id:
                                        artifact_counter += 1
                                        _save_artifact(
                                            self.session_id,
                                            f"mermaid-{artifact_counter}",
                                            str(mi + 1),
                                            {
                                                "type": "mermaid",
                                                "label": mblock["label"],
                                                "data": mblock["code"],
                                            },
                                        )
                                streaming_text = False
                                text_buf = ""

                            # Speculative summarization: kick off Gemini summary
                            # in the background while Claude may still be doing
                            # tool calls. By the time ResultMessage arrives the
                            # summary is often already ready, saving ~300ms.
                            if (
                                len(full_run_text) >= 200
                                and speculative_summary_task is None
                            ):
                                client = _get_gemini()
                                if client:
                                    truncated = _truncate_for_tts(full_run_text.strip())
                                    speculative_summary_task = asyncio.create_task(
                                        _summarize(client, truncated, True)
                                    )

                    continue

                # ── Complete assistant messages ────────────────────
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            # Deduplicate across reconnects and streaming/complete
                            if block.id in self._emitted_tool_ids:
                                continue
                            self._emitted_tool_ids.add(block.id)
                            summary = _tool_summary_sdk(block)
                            tool_summaries.append(summary)
                            await ws.send_json(
                                {
                                    "type": "tool_use",
                                    "name": block.name,
                                    "tool_use_id": block.id,
                                    "input": block.input,
                                    "summary": summary,
                                    "parent_tool_use_id": msg.parent_tool_use_id,
                                }
                            )
                            # Emit structured events for specific tool types
                            if block.name == "TodoWrite":
                                await ws.send_json(
                                    {
                                        "type": "todo_update",
                                        "todos": block.input.get("todos", []),
                                        "parent_tool_use_id": msg.parent_tool_use_id,
                                    }
                                )
                            elif block.name == "Task":
                                await ws.send_json(
                                    {
                                        "type": "subagent_start",
                                        "tool_use_id": block.id,
                                        "name": block.input.get(
                                            "name", block.input.get("description", "")
                                        ),
                                        "description": block.input.get(
                                            "description", ""
                                        ),
                                        "subagent_type": block.input.get(
                                            "subagent_type", ""
                                        ),
                                        "parent_tool_use_id": msg.parent_tool_use_id,
                                    }
                                )
                        elif isinstance(block, TextBlock) and block.text:
                            # Skip if already captured via streaming path
                            # (include_partial_messages=True causes both to fire)
                            if block.text not in streaming_captured:
                                full_run_text += block.text + "\n"
                        elif isinstance(block, ToolResultBlock):
                            content = block.content
                            images = (
                                _extract_images(content)
                                if isinstance(content, list)
                                else []
                            )
                            if isinstance(content, list):
                                content = "\n".join(
                                    b.get("text", "")
                                    for b in content
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                            result_msg = {
                                "type": "tool_result",
                                "tool_use_id": block.tool_use_id,
                                "name": getattr(block, "name", None) or "",
                                "output": str(content or "")[:5000],
                            }
                            if getattr(block, "is_error", False):
                                result_msg["is_error"] = True
                            if images:
                                result_msg["image"] = images[0]
                                # Auto-save image artifact
                                if self.session_id:
                                    artifact_counter += 1
                                    _save_artifact(
                                        self.session_id,
                                        f"tool-{artifact_counter}",
                                        "1",
                                        {
                                            "type": "image",
                                            "label": block.name or "screenshot",
                                            "data": images[0].get("data", ""),
                                            "mimeType": images[0].get(
                                                "mimeType", "image/png"
                                            ),
                                        },
                                    )
                            await ws.send_json(result_msg)
                            # Detect PR URLs in tool output
                            await _detect_prs_in_output(
                                str(content or ""), self.session_id, ws
                            )
                    continue

                # ── User messages (tool results flowing back) ─────
                if isinstance(msg, UserMessage):
                    if msg.tool_use_result:
                        tur = msg.tool_use_result
                        # MCP tool results may be a list of content blocks
                        # instead of a dict with "content" key
                        if isinstance(tur, list):
                            content = tur
                            tool_use_id = ""
                        elif isinstance(tur, dict):
                            content = tur.get("content", "")
                            tool_use_id = tur.get("tool_use_id", "")
                        else:
                            content = str(tur)
                            tool_use_id = ""
                        images = (
                            _extract_images(content)
                            if isinstance(content, list)
                            else []
                        )
                        if isinstance(content, list):
                            content = "\n".join(
                                b.get("text", "")
                                for b in content
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        result_msg = {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "output": str(content or "")[:5000],
                        }
                        if images:
                            result_msg["image"] = images[0]
                            # Auto-save image artifact
                            if self.session_id:
                                artifact_counter += 1
                                _save_artifact(
                                    self.session_id,
                                    f"user-tool-{artifact_counter}",
                                    "1",
                                    {
                                        "type": "image",
                                        "label": "screenshot",
                                        "data": images[0].get("data", ""),
                                        "mimeType": images[0].get(
                                            "mimeType", "image/png"
                                        ),
                                    },
                                )
                        await ws.send_json(result_msg)
                        # Detect PR URLs in tool output
                        await _detect_prs_in_output(
                            str(content or ""), self.session_id, ws
                        )
                    continue

                # ── Final result ──────────────────────────────────
                if isinstance(msg, ResultMessage):
                    self.session_id = msg.session_id

                    # Send any remaining streaming text
                    if streaming_text:
                        full_run_text += text_buf + "\n"
                        await ws.send_json(
                            {
                                "type": "assistant_done",
                                "full_text": text_buf,
                            }
                        )
                        streaming_text = False

                    final_text = full_run_text.strip() or (msg.result or "")
                    log.info(
                        "SDK result: session=%s, turns=%d, text_len=%d, is_error=%s, tools=%d",
                        msg.session_id,
                        msg.num_turns,
                        len(final_text),
                        msg.is_error,
                        len(tool_summaries),
                    )
                    if not final_text and tool_summaries:
                        log.warning(
                            "SDK returned tools but no text (turns=%d, is_error=%s) — "
                            "Claude may have terminated early",
                            msg.num_turns,
                            msg.is_error,
                        )
                    got_result = True
                    result_payload = {
                        "type": "result",
                        "session_id": msg.session_id,
                        "cost_usd": msg.total_cost_usd,
                        "duration_ms": msg.duration_ms,
                        "num_turns": msg.num_turns,
                        "is_error": msg.is_error,
                        "full_text": final_text,
                    }
                    if tool_summaries:
                        result_payload["tool_summaries"] = tool_summaries

                    # Attach speculative summary if ready (or wait briefly)
                    if speculative_summary_task is not None:
                        try:
                            spoken, summary, actions = await asyncio.wait_for(
                                speculative_summary_task, timeout=2.0
                            )
                            if summary:
                                result_payload["speculative_summary"] = {
                                    "summary": summary,
                                    "actions": actions or [],
                                }
                                log.info(
                                    "Speculative summary attached (%d chars)",
                                    len(summary),
                                )
                        except (asyncio.TimeoutError, Exception) as e:
                            log.info("Speculative summary not ready: %s", e)

                    await ws.send_json(result_payload)
                    continue

        except asyncio.CancelledError:
            log.info("SDK query task cancelled")
            raise
        except Exception as e:
            log.error("SDK query error: %s", e)
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass
            return True, True, msg_count  # Don't retry on exceptions

        # Preserve accumulated state for run() to use after retries exhaust.
        had_output = bool(full_run_text.strip() or tool_summaries)
        if not got_result and had_output:
            log.warning(
                "SDK ended without ResultMessage (text_len=%d, tools=%d, msgs=%d)",
                len(full_run_text.strip()),
                len(tool_summaries),
                msg_count,
            )
            if streaming_text:
                full_run_text += text_buf + "\n"
                await ws.send_json({"type": "assistant_done", "full_text": text_buf})
            self._last_run_text = full_run_text.strip()
            self._last_tool_summaries = tool_summaries

        return got_result, had_output, msg_count

    def cancel(self):
        """Signal the running query to stop."""
        self._cancel_event.set()


def _tool_summary_sdk(block: ToolUseBlock) -> str:
    """Generate a human-readable summary for a SDK ToolUseBlock."""
    name = block.name
    inp = block.input

    if name == "Edit":
        return f"Edit: {inp.get('file_path', 'file')}"
    if name == "Write":
        return f"Write: {inp.get('file_path', 'file')}"
    if name == "Read":
        return f"Read: {inp.get('file_path', 'file')}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Run: {cmd[:80]}"
    if name == "Glob":
        return f"Search: {inp.get('pattern', '')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"
    if name == "TaskCreate":
        return f"Task: {inp.get('subject', '')}"
    if name == "TaskUpdate":
        return f"TaskUpdate: #{inp.get('taskId', '')} → {inp.get('status', '')}"
    if name == "Task":
        return f"Agent: {inp.get('name', inp.get('description', ''))}"
    if name == "SendMessage":
        return f"Message → {inp.get('recipient', inp.get('type', ''))}"

    return name


# Keep old helper for session history parsing (uses dicts, not SDK types)
def _tool_summary(block: dict) -> str:
    """Generate a human-readable summary for a tool use dict (JSONL parsing)."""
    name = block.get("name", "")
    inp = block.get("input", {})

    if name == "Edit":
        return f"Edit: {inp.get('file_path', 'file')}"
    if name == "Write":
        return f"Write: {inp.get('file_path', 'file')}"
    if name == "Read":
        return f"Read: {inp.get('file_path', 'file')}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Run: {cmd[:80]}"
    if name == "Glob":
        return f"Search: {inp.get('pattern', '')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"

    return name


_MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)


def _extract_mermaid_blocks(text: str) -> list[dict]:
    """Extract mermaid code blocks from markdown text."""
    blocks = []
    for i, m in enumerate(_MERMAID_RE.finditer(text)):
        code = m.group(1).strip()
        if code:
            blocks.append({"code": code, "label": f"diagram-{i + 1}"})
    return blocks


def _extract_images(content) -> list[dict]:
    """Extract image data from SDK content blocks."""
    images = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    images.append(
                        {
                            "data": source.get("data", ""),
                            "mimeType": source.get("media_type", "image/png"),
                        }
                    )
    return images


# ── Session history endpoint ─────────────────────────────────────────────────


def _sessions_dir_for_workdir(workdir: str) -> Path:
    """Derive the Claude Code sessions directory for a given workdir.

    Claude Code stores sessions at ~/.claude/projects/<encoded-path>/*.jsonl
    where <encoded-path> is the workdir with / replaced by -.
    """
    encoded = workdir.replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def _parse_session_preview(filepath: Path, max_lines: int = 50) -> dict | None:
    """Parse a session JSONL file to extract metadata for listing."""
    sid = filepath.stem
    stat = filepath.stat()
    mtime = stat.st_mtime
    size_kb = stat.st_size // 1024

    preview = ""
    cwd = ""
    msg_count = 0

    try:
        with open(filepath) as f:
            for i, line in enumerate(f):
                if i > max_lines:
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")
                if otype == "user":
                    msg_count += 1
                    if not cwd:
                        cwd = obj.get("cwd", "")
                    if not preview:
                        content = obj.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            # Strip system-reminder tags
                            text = content
                            if "<" in text:
                                import re

                                text = re.sub(
                                    r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL
                                ).strip()
                            preview = text[:120]
                        elif isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    text = c["text"]
                                    if "<" in text:
                                        import re

                                        text = re.sub(
                                            r"<[^>]+>.*?</[^>]+>",
                                            "",
                                            text,
                                            flags=re.DOTALL,
                                        ).strip()
                                    preview = text[:120]
                                    break
                elif otype == "assistant":
                    msg_count += 1
    except Exception as e:
        log.warning("Failed to parse session %s: %s", sid, e)
        return None

    if not preview:
        return None  # Skip empty sessions

    return {
        "id": sid,
        "preview": preview,
        "cwd": cwd,
        "mtime": mtime,
        "size_kb": size_kb,
        "msg_count": msg_count,
    }


def _all_projects_dirs() -> list[Path]:
    """Return all Claude Code project directories."""
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    return [d for d in base.iterdir() if d.is_dir()]


def _find_session_file(session_id: str) -> Path | None:
    """Search all project directories for a session JSONL file."""
    for proj_dir in _all_projects_dirs():
        candidate = proj_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


@app.get("/api/sessions")
async def list_sessions(limit: int = 50, all_projects: bool = True):
    """List recent Claude Code sessions.

    By default scans all projects. Pass all_projects=false to only show
    sessions for the configured workdir.
    """
    if all_projects:
        dirs = _all_projects_dirs()
    else:
        workdir = app.state.workdir
        sessions_dir = _sessions_dir_for_workdir(workdir)
        dirs = [sessions_dir] if sessions_dir.exists() else []

    # Collect all JSONL files across project dirs, sorted by mtime
    all_files = []
    for d in dirs:
        project_name = d.name  # e.g. "-Users-jomcgi-repos-homelab"
        for f in d.glob("*.jsonl"):
            all_files.append((f, project_name))

    all_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    all_files = all_files[:limit]

    sessions = []
    for f, project_name in all_files:
        info = _parse_session_preview(f)
        if info:
            # Decode project name back to path for display
            readable_project = (
                project_name.replace("-", "/", 1)
                if project_name.startswith("-")
                else project_name
            )
            info["project"] = readable_project
            sessions.append(info)

    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 200):
    """Load conversation messages from a session JSONL file."""
    import re as _re

    filepath = _find_session_file(session_id)
    if not filepath:
        return {"messages": [], "error": "Session not found"}

    messages = []
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")

                if otype == "user":
                    content = obj.get("message", {}).get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text = c["text"]
                                break

                    # Strip system-reminder tags
                    if "<" in text:
                        text = _re.sub(
                            r"<[^>]+>.*?</[^>]+>", "", text, flags=_re.DOTALL
                        ).strip()

                    if text:
                        messages.append(
                            {
                                "role": "voice",
                                "text": text[:2000],
                            }
                        )

                elif otype == "assistant":
                    msg = obj.get("message", {})
                    for block in msg.get("content", []):
                        if (
                            block.get("type") == "text"
                            and block.get("text", "").strip()
                        ):
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "done",
                                    "text": block["text"][:2000],
                                }
                            )
                        elif block.get("type") == "tool_use":
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "tool",
                                    "text": _tool_summary(block),
                                }
                            )

                if len(messages) >= limit:
                    break

    except Exception as e:
        log.error("Failed to load session %s: %s", session_id, e)
        return {"messages": [], "error": str(e)}

    return {"messages": messages, "session_id": session_id}


# ── Artifact + Summary persistence API ────────────────────────────────────────


@app.post("/api/artifacts")
async def save_artifact(body: dict):
    """Upsert an artifact for a session message."""
    session_id = body.get("session_id")
    msg_id = body.get("msg_id")
    slot = body.get("slot", "1")
    artifact = body.get("artifact", {})
    if not session_id or not msg_id or not artifact:
        return {"error": "Missing session_id, msg_id, or artifact"}
    _save_artifact(session_id, msg_id, slot, artifact)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str):
    """Return all artifacts for a session, ordered by created_at."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        artifacts = []
        for r in rows:
            artifacts.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "msg_id": r["msg_id"],
                    "slot": r["slot"],
                    "type": r["type"],
                    "label": r["label"],
                    "data": r["data"],
                    "mimeType": r["mime_type"],
                    "meta": json.loads(r["meta"]) if r["meta"] else None,
                    "created_at": r["created_at"],
                }
            )
        return {"artifacts": artifacts}
    finally:
        db.close()


@app.post("/api/summaries")
async def save_summary_endpoint(body: dict):
    """Upsert a TTS summary for a session message."""
    session_id = body.get("session_id")
    msg_id = body.get("msg_id")
    text = body.get("text", "")
    if not session_id or not msg_id or not text:
        return {"error": "Missing session_id, msg_id, or text"}
    _save_summary(session_id, msg_id, text)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/summaries")
async def get_session_summaries(session_id: str):
    """Return all summaries for a session, ordered by created_at."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM summaries WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        summaries = []
        for r in rows:
            summaries.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "msg_id": r["msg_id"],
                    "text": r["text"],
                    "created_at": r["created_at"],
                }
            )
        return {"summaries": summaries}
    finally:
        db.close()


@app.get("/api/sessions/{session_id}/prs")
async def get_session_prs(session_id: str):
    """Return all PRs for a session, ordered by created_at."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM prs WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return {"prs": [dict(r) for r in rows]}
    finally:
        db.close()


@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str):
    """Export a full session as formatted Markdown for debugging.

    Combines JSONL messages (no limit) with artifacts and summaries from the DB.
    """
    import re as _re

    filepath = _find_session_file(session_id)
    if not filepath:
        return {"error": "Session not found", "session_id": session_id}

    # Parse all messages from JSONL (no limit)
    messages = []
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")

                if otype == "user":
                    content = obj.get("message", {}).get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text = c["text"]
                                break
                    if "<" in text:
                        text = _re.sub(
                            r"<[^>]+>.*?</[^>]+>", "", text, flags=_re.DOTALL
                        ).strip()
                    if text:
                        messages.append({"role": "voice", "text": text})

                elif otype == "assistant":
                    msg = obj.get("message", {})
                    for block in msg.get("content", []):
                        if (
                            block.get("type") == "text"
                            and block.get("text", "").strip()
                        ):
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "done",
                                    "text": block["text"],
                                }
                            )
                        elif block.get("type") == "tool_use":
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "tool",
                                    "text": _tool_summary(block),
                                }
                            )

    except Exception as e:
        log.error("Failed to load session for export %s: %s", session_id, e)
        return {"error": str(e), "session_id": session_id}

    # Load summaries from DB and append as gemini messages
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT text FROM summaries WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        # Interleave summaries after claude done messages
        summary_texts = [r["text"] for r in rows]
    finally:
        db.close()

    # Insert gemini summaries after each group's final claude message
    if summary_texts:
        enriched = []
        summary_idx = 0
        i = 0
        while i < len(messages):
            enriched.append(messages[i])
            # After a "done" claude message, check if the next message starts a new voice turn
            if (
                messages[i].get("role") == "claude"
                and messages[i].get("status") == "done"
                and summary_idx < len(summary_texts)
            ):
                # Peek ahead: is the next message a new voice turn or end of messages?
                next_is_new_turn = (
                    i + 1 >= len(messages) or messages[i + 1].get("role") == "voice"
                )
                if next_is_new_turn:
                    enriched.append(
                        {"role": "gemini", "text": summary_texts[summary_idx]}
                    )
                    summary_idx += 1
            i += 1
        messages = enriched

    # Format as markdown (server-side version of the client utility)
    groups = []
    cur = None
    for m in messages:
        if m.get("role") == "voice":
            if cur:
                groups.append(cur)
            cur = {"voice": m, "steps": [], "result": None, "summary": None}
        elif m.get("role") == "claude":
            if not cur:
                cur = {"voice": None, "steps": [], "result": None, "summary": None}
            if m.get("status") in ("thinking", "tool"):
                cur["steps"].append(m)
            elif m.get("status") == "done":
                cur["result"] = m
        elif m.get("role") == "gemini":
            if cur:
                cur["summary"] = m
                groups.append(cur)
                cur = None
    if cur:
        groups.append(cur)

    lines = [f"# Bosun Conversation Export", f"**Session:** `{session_id}`", ""]
    turns_no_response = []
    tool_errors = 0
    missing_summaries = 0

    for i, g in enumerate(groups):
        turn_num = i + 1
        lines.append("---")
        lines.append("")
        lines.append(f"## Turn {turn_num}")
        lines.append("")

        if g["voice"]:
            lines.append("### Voice Input")
            lines.append(f"> {g['voice']['text']}")
            lines.append("")

        normal_steps = [s for s in g["steps"] if not s.get("_error")]
        error_steps = [s for s in g["steps"] if s.get("_error")]
        tool_errors += len(error_steps)

        if normal_steps:
            lines.append(
                f"### Tool Use ({len(normal_steps)} step{'s' if len(normal_steps) > 1 else ''})"
            )
            for si, s in enumerate(normal_steps):
                lines.append(f"{si + 1}. {s.get('text', '(unknown)')}")
            lines.append("")

        if error_steps:
            lines.append("### Errors")
            for s in error_steps:
                lines.append(f"- **Error:** {s.get('text', '')}")
            lines.append("")

        if g["result"]:
            lines.append("### Claude Response")
            lines.append(g["result"].get("text", "*Empty response*"))
            lines.append("")
        elif g["steps"]:
            lines.append("### Claude Response")
            lines.append("**No response generated**")
            lines.append("")
            turns_no_response.append(turn_num)

        if g["summary"]:
            lines.append("### Spoken Summary")
            lines.append(f"_{g['summary']['text']}_")
            lines.append("")
        elif g["result"]:
            missing_summaries += 1

    lines.append("---")
    lines.append("")
    lines.append("## Debug Summary")
    if turns_no_response:
        lines.append(
            f"- Turns with no Claude response: {', '.join(map(str, turns_no_response))}"
        )
    else:
        lines.append("- All turns produced a Claude response")
    lines.append(f"- Tool errors: {tool_errors}")
    lines.append(
        f"- Missing Gemini summaries: {missing_summaries} / {len(groups)} turns"
    )

    return {"markdown": "\n".join(lines), "session_id": session_id}


# ── Gemini TTS + title generation ────────────────────────────────────────────

_gemini_client = None


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        if not HAS_GEMINI:
            return None
        key = GOOGLE_API_KEY
        if not key:
            return None
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _pcm_to_wav(
    pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits: int = 16
) -> bytes:
    """Wrap raw PCM audio bytes in a WAV header."""
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # file size - 8
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )
    return header + pcm_data


# ── TTS helpers and caching ────────────────────────────────────────────────

_TTS_CACHE: dict[str, str] = {}  # phrase -> base64 WAV audio
_TTS_CACHE_PATH = Path.home() / ".claude" / "tts_cache.json"

_CACHED_PHRASES = [
    "Compacting session context",
    "Starting new session",
    "Cancelled",
    "Muted",
    "Unmuted",
    "Approved",
    "Rejected",
    "Nothing to approve",
    "Nothing to reject",
    "Nothing to repeat",
    "Claude is currently working",
    "Claude is idle",
    "No recent sessions",
    "Could not load sessions",
    "Could not search sessions",
    "No matching session found",
]


def _generate_tts_raw(text: str) -> bytes | None:
    """Generate raw PCM audio from Google Cloud TTS Chirp3-HD (synchronous, for thread pool)."""
    import urllib.request

    if not GOOGLE_API_KEY:
        return None
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"
    payload = json.dumps(
        {
            "input": {"text": text},
            "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Kore"},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
        }
    ).encode()
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return base64.b64decode(data["audioContent"])
    except Exception as e:
        log.warning("TTS generation failed: %s", e)
        return None


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at . ! ? boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


async def _precache_tts():
    """Pre-generate TTS audio for static confirmation phrases.

    Loads previously cached audio from disk (PVC-backed) and only generates
    missing phrases, so pod restarts don't re-hit the TTS API.
    """
    # Load existing cache from PVC
    if _TTS_CACHE_PATH.exists():
        try:
            saved = json.loads(_TTS_CACHE_PATH.read_text())
            _TTS_CACHE.update(saved)
            log.info("TTS cache: loaded %d phrases from disk", len(saved))
        except Exception as e:
            log.warning("TTS cache: failed to load from disk: %s", e)

    missing = [p for p in _CACHED_PHRASES if p not in _TTS_CACHE]
    if not missing:
        log.info(
            "TTS cache: all %d phrases already cached on disk", len(_CACHED_PHRASES)
        )
        return

    if not GOOGLE_API_KEY:
        log.info(
            "TTS cache: GOOGLE_API_KEY not set, skipping %d missing phrases",
            len(missing),
        )
        return

    log.info("TTS cache: generating %d missing phrases...", len(missing))
    for phrase in missing:
        try:
            pcm = await asyncio.to_thread(_generate_tts_raw, phrase)
            if pcm:
                wav = _pcm_to_wav(pcm, sample_rate=24000)
                _TTS_CACHE[phrase] = base64.b64encode(wav).decode("utf-8")
        except Exception as e:
            log.warning("TTS cache: failed '%s': %s", phrase, e)

    # Persist to PVC so next restart skips generation
    try:
        _TTS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TTS_CACHE_PATH.write_text(json.dumps(_TTS_CACHE))
        log.info("TTS cache: saved %d phrases to disk", len(_TTS_CACHE))
    except Exception as e:
        log.warning("TTS cache: failed to save to disk: %s", e)

    log.info("TTS cache: cached %d/%d phrases", len(_TTS_CACHE), len(_CACHED_PHRASES))


@app.on_event("startup")
async def _startup():
    _prune_stale_sessions()
    asyncio.create_task(_precache_tts())


@app.get("/api/tts/cache")
async def get_tts_cache():
    """Return all pre-cached TTS audio for client-side instant playback."""
    return {"cache": _TTS_CACHE, "mime_type": "audio/wav"}


@app.post("/api/intent")
async def classify_intent(body: dict):
    """Classify voice input as a command or message using Gemini Flash."""
    client = _get_gemini()
    if not client:
        return {"intent": "message"}  # Fallback: treat as message

    text = body.get("text", "")
    if not text:
        return {"intent": "message"}

    context = body.get("context", {})

    prompt = (
        "You classify short voice commands for a coding assistant UI.\n"
        "The user is either giving a UI command OR a task/question for the coding agent.\n"
        "If the input sounds like a task, question, or instruction for a coding agent, "
        "reply 'message'. When in doubt, prefer 'message'.\n\n"
        f"Context: streaming={context.get('streaming')}, "
        f"approval_pending={context.get('has_pending_approval')}\n\n"
        "Available commands (ONLY match if clearly intended):\n"
        "- new_session: user wants to start a fresh conversation (e.g. 'new session', 'start over')\n"
        "- cancel: user wants to stop the current task (e.g. 'cancel', 'stop', 'nevermind')\n"
        "- repeat: user wants to hear the last response again (e.g. 'say that again', 'repeat')\n"
        "- list_sessions: user asks what sessions exist (e.g. 'list my sessions')\n"
        "- switch_session: user wants to switch to a different session (e.g. 'go back to the auth one')\n"
        "- status: user asks if the UI/agent is busy or idle (e.g. 'what's happening', 'are you busy')\n"
        "- mute/unmute: user wants to toggle spoken responses\n"
        "- approve/reject: user responds to a pending tool approval\n"
        "- compact: user wants to compress/summarize the session context\n"
        "- message: anything else -- tasks, questions, instructions for the coding agent\n\n"
        f'Voice input: "{text}"\n\n'
        "Reply with ONLY the command name. "
        "If switch_session, add |query. Example: switch_session|the auth fix\n"
        "If compact, add |directive. Example: compact|summarize the auth changes"
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        raw = response.text.strip().lower()
        if "|" in raw:
            intent, param = raw.split("|", 1)
            return {"intent": intent.strip(), "params": {"query": param.strip()}}
        return {"intent": raw if raw != "message" else "message"}
    except Exception as e:
        log.warning("Intent classification failed: %s", e)
        return {"intent": "message"}


@app.post("/api/sessions/search")
async def search_sessions(body: dict):
    """Fuzzy search sessions by natural language query using Gemini."""
    client = _get_gemini()
    search_query = body.get("query", "")
    if not client or not search_query:
        return {"matches": []}

    # Load recent session previews
    dirs = _all_projects_dirs()
    all_files = []
    for d in dirs:
        for f in d.glob("*.jsonl"):
            all_files.append(f)
    all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    all_files = all_files[:30]

    previews = []
    for f in all_files:
        info = _parse_session_preview(f)
        if info:
            previews.append(info)

    if not previews:
        return {"matches": []}

    # Ask Gemini to match
    listing = "\n".join(
        f"{i}. [{p['id'][:8]}] {p['preview'][:80]}" for i, p in enumerate(previews)
    )
    prompt = (
        f"Given these coding sessions:\n{listing}\n\n"
        f'Which session best matches the query: "{search_query}"?\n'
        "Reply with ONLY the index number (0-based). If no good match, reply -1."
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        idx = int(response.text.strip())
        if 0 <= idx < len(previews):
            return {"matches": [previews[idx]]}
        return {"matches": []}
    except Exception:
        return {"matches": []}


@app.get("/api/status")
async def get_status():
    """Return current session status for voice readback."""
    ws_endpoint = getattr(app.state, "_ws_status", {})
    return {
        "session_id": ws_endpoint.get("session_id"),
        "streaming": ws_endpoint.get("streaming", False),
        "queue_depth": ws_endpoint.get("queue_depth", 0),
        "connected": ws_endpoint.get("connected", False),
    }


def _truncate_for_tts(text: str) -> str:
    """Keep first ~500 chars + last ~1500 chars, breaking at sentence boundaries."""
    if len(text) <= 2000:
        return text
    head = text[:500]
    tail = text[-1500:]
    head_break = head.rfind(".")
    if head_break > 200:
        head = head[: head_break + 1]
    tail_break = tail.find(".")
    if 0 < tail_break < 200:
        tail = tail[tail_break + 1 :].lstrip()
    return head + "\n[...]\n" + tail


_SUMMARY_PROMPT = (
    "You are briefing a developer who is listening, not reading.\n"
    "Summarize the coding agent's output for spoken delivery.\n\n"
    "Rules:\n"
    "- Be concise. Use as few words as possible to convey the key point.\n"
    "- For short or simple outputs, just relay the answer directly.\n"
    "- For longer outputs, summarize what was done and any next step. Max 150 words.\n"
    '- Lead with the conclusion, not "The agent investigated..."\n'
    "- Include specific details (file names, values) only when the listener\n"
    "  needs them to respond without seeing the screen\n"
    "- If the agent asks the user a question, end with that question\n"
    "- Be natural and conversational — this will be spoken aloud\n"
    "- Do NOT use markdown, bullet points, or formatting\n\n"
)


async def _summarize(client, text: str, suggest_actions: bool):
    """Summarize agent output for spoken delivery. Returns (spoken_text, summary, actions)."""
    try:
        if suggest_actions:
            sa_prompt = (
                _SUMMARY_PROMPT
                + "Then suggest 1-3 follow-up actions the user might want.\n\n"
                "Output format (JSON only, no markdown):\n"
                '{"summary": "...", "actions": [{"label": "Run tests", "prompt": "run the test suite"}]}\n\n'
                f"Agent output:\n{text}"
            )
            sa_resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3-flash-preview",
                contents=sa_prompt,
            )
            raw = sa_resp.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            parsed = json.loads(raw)
            summary = parsed.get("summary", "").strip().strip('"').strip("'")
            actions = parsed.get("actions", [])
            return summary, summary, actions
        else:
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3-flash-preview",
                contents=_SUMMARY_PROMPT + f"Agent output:\n{text}",
            )
            summary = resp.text.strip().strip('"').strip("'")
            return summary, summary, []
    except Exception as e:
        log.warning("Summary failed, speaking full text: %s", e)
        return text, None, []


async def _stream_tts(
    client,
    text: str,
    summarize: bool,
    suggest_actions: bool,
    pre_summary: dict | None = None,
):
    """Stream TTS as NDJSON: first sentence audio arrives ASAP, then the rest."""
    text = _truncate_for_tts(text)

    # Step 1: Summarize (skip if pre-computed summary supplied)
    if pre_summary and pre_summary.get("summary"):
        spoken_text = pre_summary["summary"]
        summary_text = spoken_text
        actions = pre_summary.get("actions", [])
        log.info("Stream TTS using pre-computed summary: %s", spoken_text[:120])
    elif summarize or suggest_actions:
        spoken_text, summary_text, actions = await _summarize(
            client, text, suggest_actions
        )
        log.info("Stream TTS summary: %s", spoken_text[:120])
    else:
        spoken_text, summary_text, actions = text, None, []

    # Step 2: Split into sentences for pipelining
    sentences = _split_sentences(spoken_text)

    if len(sentences) <= 1:
        # Short — single TTS call
        pcm = await asyncio.to_thread(_generate_tts_raw, spoken_text)
        if pcm:
            wav = _pcm_to_wav(pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )
    else:
        # Pipeline: first sentence + rest run concurrently
        first_sentence = sentences[0]
        rest = " ".join(sentences[1:])

        first_task = asyncio.create_task(
            asyncio.to_thread(_generate_tts_raw, first_sentence)
        )
        rest_task = asyncio.create_task(asyncio.to_thread(_generate_tts_raw, rest))

        # Yield first sentence audio ASAP
        first_pcm = await first_task
        if first_pcm:
            wav = _pcm_to_wav(first_pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )

        # Yield remaining audio
        rest_pcm = await rest_task
        if rest_pcm:
            wav = _pcm_to_wav(rest_pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )

    # Final metadata
    result = {"done": True}
    if summary_text:
        result["summary"] = summary_text
    if actions:
        result["actions"] = actions
    yield json.dumps(result) + "\n"


@app.post("/api/tts")
async def text_to_speech(body: dict):
    """Generate speech audio from text using Google Cloud TTS (Chirp3-HD).

    Supports streaming (stream=true) for pipelined TTS: first sentence audio
    arrives while remaining sentences are still being generated.
    Summarization (if requested) uses Gemini Flash.
    """
    if not GOOGLE_API_KEY:
        return {"error": "GOOGLE_API_KEY not configured"}

    client = _get_gemini()  # needed for summarization only

    text = body.get("text", "").strip()
    if not text:
        return {"error": "No text provided"}

    # Check pre-cache for exact matches (static confirmations)
    if text in _TTS_CACHE:
        return {"audio": _TTS_CACHE[text], "mime_type": "audio/wav"}

    summarize = body.get("summarize", False)
    suggest_actions = body.get("suggest_actions", False)
    pre_summary = body.get("pre_summary")  # From speculative summarization

    # Streaming mode: NDJSON with pipelined audio chunks
    if body.get("stream"):
        return StreamingResponse(
            _stream_tts(client, text, summarize, suggest_actions, pre_summary),
            media_type="application/x-ndjson",
        )

    # Non-streaming (legacy) path
    text = _truncate_for_tts(text)

    if summarize or suggest_actions:
        spoken_text, summary_text, actions = await _summarize(
            client, text, suggest_actions
        )
        log.info("TTS summary: %s", spoken_text[:120])
    else:
        spoken_text, summary_text, actions = text, None, []

    try:
        pcm = await asyncio.to_thread(_generate_tts_raw, spoken_text)
        if not pcm:
            return {"error": "TTS generation failed"}
        wav_audio = _pcm_to_wav(pcm, sample_rate=24000)
        audio_b64 = base64.b64encode(wav_audio).decode("utf-8")
        result = {"audio": audio_b64, "mime_type": "audio/wav"}
        if summary_text:
            result["summary"] = summary_text
        if actions:
            result["actions"] = actions
        return result

    except Exception as e:
        log.error("Cloud TTS error: %s", e)
        return {"error": str(e)}


@app.post("/api/title")
async def generate_title(body: dict):
    """Generate a short session title from conversation messages using Gemini."""
    client = _get_gemini()
    if not client:
        return {"error": "Gemini not configured"}

    messages = body.get("messages", [])
    if not messages:
        return {"error": "No messages provided"}

    # Build a condensed transcript
    transcript = ""
    for m in messages[:10]:  # First 10 messages max
        role = "User" if m.get("role") == "voice" else "Claude"
        text = m.get("text", "")[:200]
        transcript += f"{role}: {text}\n"

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=f"Generate a short title (3-6 words, no quotes) summarizing this coding session:\n\n{transcript}",
        )
        title = response.text.strip().strip('"').strip("'")
        return {"title": title}

    except Exception as e:
        log.error("Gemini title error: %s", e)
        return {"error": str(e)}


# ── WebSocket endpoint ──────────────────────────────────────────────────────


async def _compact_session(session_id: str | None, directive: str = "") -> str:
    """Summarize a session's conversation via Gemini for context compaction."""
    client = _get_gemini()
    if not client or not session_id:
        return ""

    filepath = _find_session_file(session_id)
    if not filepath:
        return ""

    # Load last N messages from session JSONL
    messages_text = []
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                otype = obj.get("type", "")
                if otype == "user":
                    content = obj.get("message", {}).get("content", "")
                    if isinstance(content, str) and content.strip():
                        messages_text.append(f"User: {content[:200]}")
                elif otype == "assistant":
                    for block in obj.get("message", {}).get("content", []):
                        if (
                            block.get("type") == "text"
                            and block.get("text", "").strip()
                        ):
                            messages_text.append(f"Assistant: {block['text'][:200]}")
    except Exception as e:
        log.warning("Failed to read session for compaction: %s", e)
        return ""

    # Take last 30 messages to stay within Gemini context
    recent = messages_text[-30:]
    transcript = "\n".join(recent)

    focus = f" Focus on: {directive}" if directive else ""
    prompt = (
        f"Summarize this coding session concisely.{focus}\n"
        "Include: what was worked on, key decisions made, current state, and any pending tasks.\n"
        "Keep it under 300 words.\n\n"
        f"{transcript}"
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        log.warning("Session compaction failed: %s", e)
        return ""


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket connected")

    workdir = app.state.workdir
    session = ClaudeSession(workdir)
    current_task: asyncio.Task | None = None
    message_queue: list[str] = []  # Queued messages for when agent is busy
    pr_poll_task: asyncio.Task | None = None  # PR state polling

    # Expose status for the /api/status endpoint
    def _update_status():
        app.state._ws_status = {
            "session_id": session.session_id,
            "streaming": current_task is not None and not current_task.done(),
            "queue_depth": len(message_queue),
            "connected": True,
        }

    _update_status()

    async def drain_queue():
        """Process queued messages sequentially after the current turn finishes."""
        while message_queue:
            next_text = message_queue.pop(0)
            _update_status()
            log.info(
                "Draining queued message (%d remaining): %s...",
                len(message_queue),
                next_text[:60],
            )
            await ws.send_json(
                {
                    "type": "queue_drain",
                    "text": next_text,
                    "remaining": len(message_queue),
                }
            )
            await session.run(next_text, ws)

    async def run_and_drain(text: str):
        """Run a prompt then drain any queued follow-ups."""
        nonlocal pr_poll_task
        _update_status()
        await session.run(text, ws)
        _update_status()
        # Start PR polling once we have a session_id
        if session.session_id and (pr_poll_task is None or pr_poll_task.done()):
            pr_poll_task = asyncio.create_task(_poll_prs(ws, session.session_id))
        await drain_queue()

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue

                # Inject TTS summary context so Claude knows what the user heard
                summary_ctx = data.get("summary_context", "").strip()
                if summary_ctx:
                    text = (
                        f"[The user heard this spoken summary of your last response: "
                        f'"{summary_ctx}"]\n\n{text}'
                    )

                if current_task and not current_task.done():
                    # Agent is busy — queue the message for delivery after current turn
                    message_queue.append(text)
                    _update_status()
                    log.info(
                        "Queued message (%d in queue): %s...",
                        len(message_queue),
                        text[:60],
                    )
                    await ws.send_json(
                        {
                            "type": "queued",
                            "text": text,
                            "position": len(message_queue),
                        }
                    )
                else:
                    # Agent is idle — run immediately
                    current_task = asyncio.create_task(run_and_drain(text))
                    _update_status()

            elif msg_type == "clear_queue":
                # Clear queued messages without cancelling current task
                cleared = len(message_queue)
                message_queue.clear()
                _update_status()
                if cleared:
                    log.info("Cleared %d queued message(s)", cleared)

            elif msg_type == "cancel":
                # Explicit cancel — signal query to stop, clear queue
                message_queue.clear()
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                _update_status()
                await ws.send_json({"type": "cancelled"})
                log.info("Cancelled current task and cleared queue")

            elif msg_type == "resume":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid
                    # Restore workdir if a matching session worktree exists
                    if SESSIONS_PATH:
                        for candidate_name in [sid, f"s-{sid}", session._session_name]:
                            candidate = os.path.join(SESSIONS_PATH, candidate_name)
                            if os.path.isdir(candidate):
                                session.workdir = candidate
                                log.info(
                                    "Restored workdir for resumed session: %s",
                                    candidate,
                                )
                                break
                    # (Re)start PR polling for this session
                    if pr_poll_task and not pr_poll_task.done():
                        pr_poll_task.cancel()
                    pr_poll_task = asyncio.create_task(_poll_prs(ws, sid))
                    _update_status()
                    log.info("Resuming session: %s", sid)

            elif msg_type == "new_session":
                # Cancel any running task and clear queue
                message_queue.clear()
                if pr_poll_task and not pr_poll_task.done():
                    pr_poll_task.cancel()
                    pr_poll_task = None
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                session = ClaudeSession(workdir)
                _update_status()
                log.info("New session created")

            elif msg_type == "compact":
                # Compact current session: summarize via Gemini, start fresh
                directive = data.get("message", "")
                log.info(
                    "Compacting session (directive: %s)",
                    directive[:60] if directive else "none",
                )

                # Cancel current task if running
                message_queue.clear()
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                # Build summary of current conversation
                old_sid = session.session_id
                summary = await _compact_session(old_sid, directive)

                # Create fresh session seeded with the summary
                session = ClaudeSession(workdir)
                _update_status()

                if summary:
                    seed_prompt = f"[Context from previous session]\n{summary}\n\n[Continue from here]"
                    current_task = asyncio.create_task(run_and_drain(seed_prompt))
                    _update_status()
                    await ws.send_json({"type": "compacted", "old_session_id": old_sid})
                else:
                    await ws.send_json(
                        {
                            "type": "compacted",
                            "old_session_id": old_sid,
                            "warning": "No summary generated",
                        }
                    )

            elif msg_type == "status":
                # Return current status over WS for voice readback
                await ws.send_json(
                    {
                        "type": "status_response",
                        "session_id": session.session_id,
                        "streaming": current_task is not None
                        and not current_task.done(),
                        "queue_depth": len(message_queue),
                    }
                )

    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.error("WebSocket error: %s", e)
    finally:
        message_queue.clear()
        app.state._ws_status = {"connected": False}
        if pr_poll_task and not pr_poll_task.done():
            pr_poll_task.cancel()
        if current_task and not current_task.done():
            session.cancel()
            current_task.cancel()


# ── Static file serving (production mode) ───────────────────────────────────

STATIC_DIR = Path(__file__).parent / "dist"

if STATIC_DIR.exists():

    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


# ── CLI entry point ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Bosun backend server")
    parser.add_argument(
        "--port", type=int, default=8420, help="Server port (default: 8420)"
    )
    parser.add_argument(
        "--workdir",
        type=str,
        default=os.environ.get("DEFAULT_WORKING_DIR", "") or os.getcwd(),
        help="Working directory for Claude Code",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    app.state.workdir = os.path.abspath(args.workdir)
    log.info("Working directory: %s", app.state.workdir)
    log.info("Starting server at http://%s:%d", args.host, args.port)

    if not STATIC_DIR.exists():
        log.info(
            "No dist/ found — run 'npm run build' or use Vite dev server for frontend"
        )
        log.info("  Vite dev: cd tools/bosun && npm run dev")
        log.info("  Vite proxies /ws to this backend automatically")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

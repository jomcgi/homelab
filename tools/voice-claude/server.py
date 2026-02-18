#!/usr/bin/env python3
"""
Voice Claude — FastAPI backend bridging the web UI to Claude Code CLI.

Runs `claude -p` as a subprocess with streaming JSON output,
forwarding events to the browser over WebSocket.

Usage:
    pip install fastapi "uvicorn[standard]"
    python server.py [--port 8420] [--workdir /path/to/project]

Or with Vite dev server (for hot reload):
    # Terminal 1: python server.py --port 8420
    # Terminal 2: cd tools/voice-claude && npm run dev
    # Vite proxies /ws to the backend (see vite.config.js)
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    sys.exit("Install dependencies: pip install fastapi 'uvicorn[standard]'")

# Optional Gemini TTS
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("voice-claude")

# ── Config ──────────────────────────────────────────────────────────────────

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# Tools that are auto-approved (no user prompt needed)
AUTO_APPROVED_TOOLS = [
    "Read", "Glob", "Grep", "WebSearch", "WebFetch",
    "Bash", "Edit", "Write",  # auto-approve for prototype; tighten later
]

app = FastAPI()

# ── Claude Code subprocess manager ──────────────────────────────────────────


class ClaudeSession:
    """Manages a single claude -p subprocess and streams results."""

    def __init__(self, workdir: str):
        self.workdir = workdir
        self.session_id: str | None = None
        self.process: asyncio.subprocess.Process | None = None

    async def run(self, prompt: str, ws: WebSocket, resume_id: str | None = None):
        """Run a claude -p command and stream output to the WebSocket."""
        cmd = [
            CLAUDE_BIN, "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--allowedTools", ",".join(AUTO_APPROVED_TOOLS),
        ]

        # Resume session if we have one
        sid = resume_id or self.session_id
        if sid:
            cmd.extend(["--resume", sid])

        log.info("Running: %s", " ".join(cmd[:6]) + "...")

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workdir,
        )

        text_buf = ""
        full_run_text = ""  # Accumulate all text across the entire run
        sent_start = False

        try:
            async for raw_line in self.process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Non-JSON line: %s", line[:120])
                    continue

                etype = event.get("type")

                # ── Session init ────────────────────────────────────
                if etype == "system" and event.get("subtype") == "init":
                    self.session_id = event.get("session_id")
                    await ws.send_json({
                        "type": "session_init",
                        "session_id": self.session_id,
                    })
                    continue

                # ── Streaming text deltas ───────────────────────────
                if etype == "stream_event":
                    se = event.get("event", {})
                    se_type = se.get("type")

                    if se_type == "content_block_start":
                        cb = se.get("content_block", {})
                        if cb.get("type") == "text":
                            if not sent_start:
                                await ws.send_json({"type": "assistant_start"})
                                sent_start = True
                                text_buf = ""
                        elif cb.get("type") == "tool_use":
                            tool_name = cb.get("name", "")
                            tool_id = cb.get("id", "")
                            await ws.send_json({
                                "type": "tool_use",
                                "name": tool_name,
                                "tool_use_id": tool_id,
                                "summary": f"Using {tool_name}",
                            })

                    elif se_type == "content_block_delta":
                        delta = se.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            text_buf += chunk
                            await ws.send_json({
                                "type": "assistant_text",
                                "content": chunk,
                            })
                        elif delta.get("type") == "input_json_delta":
                            pass  # Tool input JSON streaming — skip for now

                    elif se_type == "message_stop":
                        if sent_start:
                            full_run_text += text_buf + "\n"
                            await ws.send_json({
                                "type": "assistant_done",
                                "full_text": text_buf,
                            })
                            sent_start = False
                            text_buf = ""

                    continue

                # ── Complete assistant message (with tool results) ──
                if etype == "assistant":
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "tool_use":
                            await ws.send_json({
                                "type": "tool_use",
                                "name": block.get("name", ""),
                                "tool_use_id": block.get("id", ""),
                                "input": block.get("input", {}),
                                "summary": _tool_summary(block),
                            })
                    continue

                # ── Tool results ────────────────────────────────────
                if etype == "tool_result":
                    content = event.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            b.get("text", "") for b in content if b.get("type") == "text"
                        )
                    await ws.send_json({
                        "type": "tool_result",
                        "tool_use_id": event.get("tool_use_id", ""),
                        "name": event.get("name", ""),
                        "output": str(content)[:5000],  # Truncate large outputs
                    })
                    continue

                # ── Final result ────────────────────────────────────
                if etype == "result":
                    result_text = event.get("result", "")
                    cost = event.get("total_cost_usd", 0)
                    duration = event.get("duration_ms", 0)
                    self.session_id = event.get("session_id", self.session_id)

                    # Send any remaining text as done
                    if sent_start:
                        full_run_text += text_buf + "\n"
                        await ws.send_json({
                            "type": "assistant_done",
                            "full_text": text_buf,
                        })
                        sent_start = False

                    await ws.send_json({
                        "type": "result",
                        "session_id": self.session_id,
                        "cost_usd": cost,
                        "duration_ms": duration,
                        "full_text": full_run_text.strip(),
                    })
                    continue

        except asyncio.CancelledError:
            log.info("Stream cancelled")
            self.kill()
            raise
        except Exception as e:
            log.error("Stream error: %s", e)
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

        # Wait for process to finish
        await self.process.wait()

        # Check stderr for errors
        if self.process.returncode != 0:
            stderr = await self.process.stderr.read()
            err_text = stderr.decode("utf-8", errors="replace").strip()
            if err_text:
                log.error("Claude stderr: %s", err_text[:500])
                try:
                    await ws.send_json({"type": "error", "message": err_text[:500]})
                except Exception:
                    pass

    def kill(self):
        """Kill the subprocess if running."""
        if self.process and self.process.returncode is None:
            try:
                self.process.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass


def _tool_summary(block: dict) -> str:
    """Generate a human-readable summary for a tool use block."""
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

    return f"{name}"


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
                                text = re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL).strip()
                            preview = text[:120]
                        elif isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    text = c["text"]
                                    if "<" in text:
                                        import re
                                        text = re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL).strip()
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


@app.get("/api/sessions")
async def list_sessions(limit: int = 30):
    """List recent Claude Code sessions for the configured workdir."""
    workdir = app.state.workdir
    sessions_dir = _sessions_dir_for_workdir(workdir)

    if not sessions_dir.exists():
        return {"sessions": [], "sessions_dir": str(sessions_dir)}

    files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = files[:limit]

    sessions = []
    for f in files:
        info = _parse_session_preview(f)
        if info:
            sessions.append(info)

    return {"sessions": sessions, "sessions_dir": str(sessions_dir)}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 200):
    """Load conversation messages from a session JSONL file."""
    import re as _re

    workdir = app.state.workdir
    sessions_dir = _sessions_dir_for_workdir(workdir)
    filepath = sessions_dir / f"{session_id}.jsonl"

    if not filepath.exists():
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
                        text = _re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=_re.DOTALL).strip()

                    if text:
                        messages.append({
                            "role": "voice",
                            "text": text[:2000],
                        })

                elif otype == "assistant":
                    msg = obj.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "text" and block.get("text", "").strip():
                            messages.append({
                                "role": "claude",
                                "status": "done",
                                "text": block["text"][:2000],
                            })
                        elif block.get("type") == "tool_use":
                            messages.append({
                                "role": "claude",
                                "status": "tool",
                                "text": _tool_summary(block),
                            })

                if len(messages) >= limit:
                    break

    except Exception as e:
        log.error("Failed to load session %s: %s", session_id, e)
        return {"messages": [], "error": str(e)}

    return {"messages": messages, "session_id": session_id}


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


import struct


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw PCM audio bytes in a WAV header."""
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,   # file size - 8
        b"WAVE",
        b"fmt ",
        16,               # fmt chunk size
        1,                # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )
    return header + pcm_data


@app.post("/api/tts")
async def text_to_speech(body: dict):
    """Generate speech audio from text using Gemini.

    Returns WAV audio as base64 or raw bytes.
    """
    client = _get_gemini()
    if not client:
        return {"error": "Gemini not configured (set GOOGLE_API_KEY)"}

    text = body.get("text", "")
    if not text:
        return {"error": "No text provided"}

    # Truncate to keep TTS snappy
    if len(text) > 500:
        cut = text[:500]
        last_period = cut.rfind(".")
        text = cut[:last_period + 1] if last_period > 100 else cut + "..."

    # If summarize requested, condense the text to a CTA-style summary first
    summarize = body.get("summarize", False)
    spoken_text = text
    summary_text = None

    if summarize:
        try:
            summary_resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=(
                    "You are a concise assistant summarizing what a coding agent just did. "
                    "Generate a single sentence (max 25 words) summarizing the outcome and "
                    "what the user should do next (call to action). Be direct and natural, "
                    "as this will be spoken aloud. No quotes, no markdown.\n\n"
                    f"Agent output:\n{text}"
                ),
            )
            summary_text = summary_resp.text.strip().strip('"').strip("'")
            spoken_text = summary_text
            log.info("TTS summary: %s", spoken_text)
        except Exception as e:
            log.warning("Summary failed, speaking full text: %s", e)

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash-preview-tts",
            contents=spoken_text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Kore"
                        )
                    )
                ),
            ),
        )

        # TTS model always returns raw PCM (24kHz, 16-bit, mono)
        audio_data = response.candidates[0].content.parts[0].inline_data.data
        wav_audio = _pcm_to_wav(audio_data, sample_rate=24000)
        audio_b64 = base64.b64encode(wav_audio).decode("utf-8")
        result = {
            "audio": audio_b64,
            "mime_type": "audio/wav",
        }
        if summary_text:
            result["summary"] = summary_text
        return result

    except Exception as e:
        log.error("Gemini TTS error: %s", e)
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
            model="gemini-2.5-flash",
            contents=f"Generate a short title (3-6 words, no quotes) summarizing this coding session:\n\n{transcript}",
        )
        title = response.text.strip().strip('"').strip("'")
        return {"title": title}

    except Exception as e:
        log.error("Gemini title error: %s", e)
        return {"error": str(e)}


# ── WebSocket endpoint ──────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket connected")

    workdir = app.state.workdir
    session = ClaudeSession(workdir)
    current_task: asyncio.Task | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue

                # Cancel any running task
                if current_task and not current_task.done():
                    current_task.cancel()
                    session.kill()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                # Run claude in background
                current_task = asyncio.create_task(session.run(text, ws))

            elif msg_type == "resume":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid
                    log.info("Resuming session: %s", sid)

            elif msg_type == "new_session":
                # Cancel any running task
                if current_task and not current_task.done():
                    current_task.cancel()
                    session.kill()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                session = ClaudeSession(workdir)
                log.info("New session created")

    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.error("WebSocket error: %s", e)
    finally:
        if current_task and not current_task.done():
            current_task.cancel()
            session.kill()


# ── Static file serving (production mode) ───────────────────────────────────

STATIC_DIR = Path(__file__).parent / "dist"

if STATIC_DIR.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


# ── CLI entry point ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Voice Claude backend server")
    parser.add_argument("--port", type=int, default=8420, help="Server port (default: 8420)")
    parser.add_argument("--workdir", type=str, default=os.getcwd(), help="Working directory for Claude Code")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    args = parser.parse_args()

    app.state.workdir = os.path.abspath(args.workdir)
    log.info("Working directory: %s", app.state.workdir)
    log.info("Starting server at http://%s:%d", args.host, args.port)

    if not STATIC_DIR.exists():
        log.info("No dist/ found — run 'npm run build' or use Vite dev server for frontend")
        log.info("  Vite dev: cd tools/voice-claude && npm run dev")
        log.info("  Vite proxies /ws to this backend automatically")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

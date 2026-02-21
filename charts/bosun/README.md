# Bosun

A voice-first web interface for Claude Code. Speak to your coding agent, hear spoken summaries, and control sessions entirely hands-free.

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- (Optional) `GOOGLE_API_KEY` for Gemini TTS and intent classification

### Install

```bash
cd tools/bosun

# Frontend
npm install

# Backend
python -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" google-genai
```

### Run

```bash
# Both servers together (recommended)
npm run dev

# Or separately
npm run dev:server   # FastAPI on :8420
npm run dev:ui       # Vite on :5173
```

Open http://localhost:5173. Click the mic button to start.

### Production

```bash
npm run build
python server.py --port 8420 --workdir /path/to/project
```

The server serves the built `dist/` directory and the WebSocket endpoint on the same port.

## Voice Commands

Voice input is classified through three tiers for responsiveness:

1. **Fast path** -- client-side regex, executes in <1ms with instant browser TTS confirmation
2. **Gemini classification** -- short ambiguous phrases (<20 words) are classified by Gemini Flash in ~300ms
3. **Direct to Claude** -- long utterances (>20 words) skip classification and go straight to the agent

### Quick Commands (Fast Path)

These trigger instantly via client-side pattern matching:

| Say this | What happens |
|---|---|
| "new session" / "start over" / "fresh start" | Creates a new Claude session |
| "cancel" / "stop" / "nevermind" | Cancels the current task and clears the queue |
| "say that again" / "repeat" / "read that again" | Replays the last TTS audio |
| "mute" / "be quiet" / "shut up" | Disables spoken responses |
| "unmute" / "speak" / "talk to me" | Enables spoken responses |
| "approve" / "yes" / "do it" / "go ahead" | Approves a pending tool use |
| "reject" / "no" / "don't" / "nope" | Rejects a pending tool use |
| "what's happening" / "are you busy" / "are you working" | Speaks whether Claude is working or idle |

### Gemini-Classified Commands

Short phrases that don't match the fast path are classified by Gemini Flash:

| Intent | Example phrases | What happens |
|---|---|---|
| `list_sessions` | "list sessions", "what sessions do I have?" | Speaks the 3 most recent session previews |
| `switch_session` | "go back to the one about auth", "switch to the refactor session" | Fuzzy-searches sessions and switches to the best match |
| `compact` | "compact", "compact summarize the auth changes" | Summarizes the current session via Gemini and starts fresh with that context |

If Gemini classifies the input as `message`, it is forwarded to Claude as a normal prompt.

### Wake Word: "Hey Claude"

Say **"Hey Claude"** followed by anything to skip the 2-second silence debounce and send immediately:

```
"Hey Claude, list the files in src"     --> sends "list the files in src" instantly
"Hey Claude, run the tests"             --> sends "run the tests" instantly
```

The mic button flashes purple when the wake word is detected.

#### "Hey Claude Compact"

A special subcommand of the wake word that compacts the current session:

```
"Hey Claude compact"                            --> default compaction
"Hey Claude compact summarize the auth changes" --> compaction focused on auth
```

Compaction works by:
1. Summarizing the current conversation via Gemini Flash
2. Starting a new Claude session seeded with that summary
3. Confirming via browser TTS: "Compacting session context"

This is useful when the session context grows large and you want to continue with a clean slate.

## Action Chips

After Claude finishes a task, the TTS response includes suggested follow-up actions rendered as clickable chips below the spoken summary. Clicking a chip sends its prompt to Claude.

For example, after Claude edits a file, you might see:

> **Run tests** | **Show the diff** | **Commit changes**

## Architecture

```
Browser (React + Web Speech API)
  |
  |-- Voice input ---------> useVoiceCommands
  |                            |-- regex match? --> execute locally + browser TTS
  |                            |-- short phrase? --> POST /api/intent (Gemini)
  |                            |-- long text? ----> WebSocket message to Claude
  |
  |-- WebSocket /ws -------> FastAPI (server.py)
  |                            |-- Claude Agent SDK session
  |                            |-- Streams events back to browser
  |
  |-- POST /api/tts -------> Gemini TTS (summary + audio + action chips)
  |-- POST /api/intent -----> Gemini Flash (intent classification)
  |-- GET  /api/sessions ---> Session history from ~/.claude/projects/
  |-- GET  /api/status -----> Live session status
```

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Bidirectional streaming to Claude Agent SDK |
| `/api/sessions` | GET | List recent sessions across all projects |
| `/api/sessions/{id}/messages` | GET | Load conversation history for a session |
| `/api/sessions/search` | POST | Fuzzy search sessions by natural language query |
| `/api/intent` | POST | Classify voice input as command or message |
| `/api/status` | GET | Current session status (streaming, queue depth) |
| `/api/tts` | POST | Text-to-speech with optional summary and action suggestions |
| `/api/title` | POST | Generate a short session title from messages |

### WebSocket Message Types

**Client to server:**

| Type | Fields | Description |
|---|---|---|
| `message` | `text` | Send a prompt to Claude |
| `cancel` | -- | Cancel the current task and clear queue |
| `new_session` | -- | Start a fresh session |
| `resume` | `session_id` | Resume an existing session |
| `approve` | `tool_use_id` | Approve a pending tool use |
| `reject` | `tool_use_id` | Reject a pending tool use |
| `compact` | `message` (optional directive) | Compact current session via Gemini summary |
| `status` | -- | Request current status |

**Server to client:**

| Type | Key Fields | Description |
|---|---|---|
| `session_init` | `session_id` | Session created/resumed |
| `assistant_start` | -- | Claude began generating |
| `assistant_text` | `content` | Streaming text delta |
| `assistant_done` | `full_text` | Text block complete |
| `tool_use` | `name`, `tool_use_id`, `summary` | Tool invocation |
| `tool_result` | `tool_use_id`, `output` | Tool output |
| `result` | `session_id`, `cost_usd`, `duration_ms`, `full_text` | Turn complete |
| `queued` | `text`, `position` | Message queued (agent busy) |
| `queue_drain` | `text`, `remaining` | Queued message now executing |
| `cancelled` | -- | Task was cancelled |
| `compacted` | `old_session_id` | Session was compacted |
| `status_response` | `session_id`, `streaming`, `queue_depth` | Status readback |
| `error` | `message` | Error occurred |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | No | Enables Gemini TTS, intent classification, and session search. Without it, browser `SpeechSynthesis` is used as fallback and intent classification is disabled (all input goes to Claude). |
| `CLAUDE_BIN` | No | Path to the `claude` CLI binary. Auto-detected from `/opt/homebrew/bin/claude`, `/usr/local/bin/claude`, or `$PATH`. |

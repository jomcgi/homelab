# Chat Bot Design

**Date:** 2026-03-12
**Status:** Proposed
**Author:** jomcgi + Claude

## Problem

The homelab has no central interface for interacting with cluster services from chat platforms. Cluster-agents run autonomous monitoring but have no way to notify humans. Research jobs require the orchestrator web UI or API — there's no conversational entry point.

## Goals

1. Provide a command-based Discord bot that accepts research job requests via mentions
2. Tiered access: owner requests go through the orchestrator (Claude/Goose), everyone else gets immediate responses from the local LLM (llama-cpp)
3. Enable outbound notifications from cluster-agents and recipes to Discord via NATS
4. Multi-platform ready — architecture supports adding Slack, Teams, etc. later

## Non-Goals

- Conversational AI assistant (command-only for v1)
- Slash commands or rich Discord interactions (mentions only)
- Multi-server Discord support (single server)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Discord                              │
│  @bot <message>                    ← reply with result   │
└────────┬───────────────────────────────────▲─────────────┘
         │                                   │
┌────────▼───────────────────────────────────┴─────────────┐
│                  Chat Bot (TypeScript)                     │
│  projects/agent_platform/chat_bot/                        │
│                                                           │
│  Chat SDK ─── Discord Adapter (Gateway WebSocket)         │
│     │                                                     │
│     ├─ onMention ─→ identify user                         │
│     │    ├─ owner? ─→ POST /jobs to orchestrator          │
│     │    │            store jobID→messageRef in NATS KV   │
│     │    │            reply "Working on it..."            │
│     │    └─ other? ─→ call llama-cpp /v1/chat/completions │
│     │                 reply immediately with response     │
│     │                                                     │
│     └─ NATS subscriber                                    │
│          ├─ notifications.* ─→ post to Discord channel    │
│          └─ jobs.completed  ─→ look up messageRef         │
│                               reply with summary + gist   │
└───────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   Orchestrator API      llama-cpp API        NATS JetStream
   (agent-platform ns)   (llama-cpp ns)       (agent-platform ns)
   POST /jobs            /v1/chat/completions  KV: chat-bot-state
   GET /jobs/{id}/output                       Stream: notifications
```

### Two Inbound Paths

**Owner path (async):**

1. Bot receives mention, identifies author by Discord user ID
2. Replies immediately: "Researching..."
3. Submits `POST /jobs` to orchestrator with message text as the task
4. Stores `{jobID → channelID, messageID}` in NATS KV bucket `chat-bot-state`
5. On job completion: creates GitHub gist with full output, replies to original message with summary + gist link

**Everyone else (sync):**

1. Bot receives mention, identifies author
2. Calls `POST /v1/chat/completions` on llama-cpp with the message as prompt
3. Replies directly with the response — no job, no gist

### Outbound Notifications

Cluster-agents and recipes publish to NATS for Discord delivery.

**NATS subjects:**

```
notifications.discord.<channel-name>   # Targeted to a specific channel
notifications.discord.default          # Falls back to NOTIFICATION_CHANNEL_ID
```

**Message format:**

```json
{
  "title": "Alert: Pod CrashLooping",
  "body": "signoz-otel-collector restarted 5 times in 10m",
  "severity": "warning",
  "source": "patrol-agent",
  "metadata": {}
}
```

**Subscriber behavior:**

1. Subscribes to `notifications.discord.>` (NATS wildcard)
2. Extracts channel name from subject, maps to Discord channel ID via config
3. Formats message (severity → color-coded embed) and posts

**Cluster-agents integration:** Add a `NotificationPublisher` to cluster-agents that publishes to NATS. Agents call `publisher.Notify(ctx, channel, message)`.

## Service Structure

```
projects/agent_platform/
└── chat_bot/
    ├── src/
    │   ├── index.ts          # Entry point — Chat SDK init, adapter setup
    │   ├── handlers.ts       # onMention handler, user identification
    │   ├── orchestrator.ts   # Orchestrator API client
    │   ├── llm.ts            # llama-cpp OpenAI-compatible client
    │   ├── nats.ts           # NATS subscriber (notifications, job results)
    │   └── config.ts         # Env var config
    ├── package.json
    ├── tsconfig.json
    ├── BUILD
    ├── image/
    │   └── apko.yaml         # Container image spec
    └── deploy/
        ├── application.yaml  # ArgoCD Application → own namespace
        ├── Chart.yaml
        ├── kustomization.yaml
        ├── values.yaml
        └── templates/
            ├── deployment.yaml
            ├── service.yaml
            └── onepassworditem.yaml
```

### Deployment Model

Follows the same pattern as cluster-agents:

- Own ArgoCD Application: `chat-bot`
- Own namespace: `chat-bot`
- Chart pushed to `ghcr.io/jomcgi/homelab/charts/chat-bot`
- Release name: `chat-bot`

### Cross-Namespace Connectivity

All injected via env vars in `values.yaml` — no hardcoded URLs in code:

- Orchestrator: `agent-platform-agent-orchestrator.agent-platform.svc.cluster.local:8080`
- llama-cpp: `llama-cpp.llama-cpp.svc.cluster.local:8080`
- NATS: `agent-platform-nats.agent-platform.svc.cluster.local:4222`

## Technology

- **Runtime:** TypeScript, Chat SDK (Vercel, open source, beta)
- **Discord:** `@chat-adapter/discord` — Gateway WebSocket for message events
- **State:** NATS KV bucket `chat-bot-state` for job-to-message mapping
- **Container:** apko-based Node.js image, non-root (uid 65532), dual-arch
- **Build:** Bazel (rules_js, rules_apko)

## Configuration & Secrets

### 1Password Secrets (via OnePasswordItem CRD)

- `discord-bot-credentials` → `DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`, `DISCORD_APPLICATION_ID`
- `github-token` → for gist creation (may reuse existing agent-platform token)

### Environment Variables

| Variable                   | Source      | Description                               |
| -------------------------- | ----------- | ----------------------------------------- |
| `DISCORD_BOT_TOKEN`        | 1Password   | Bot authentication                        |
| `DISCORD_PUBLIC_KEY`       | 1Password   | Interaction verification                  |
| `DISCORD_APPLICATION_ID`   | 1Password   | Application ID                            |
| `OWNER_DISCORD_USER_ID`    | values.yaml | Owner's Discord user ID for tiered access |
| `ORCHESTRATOR_URL`         | values.yaml | Orchestrator API endpoint                 |
| `LLAMA_CPP_URL`            | values.yaml | llama-cpp API endpoint                    |
| `NATS_URL`                 | values.yaml | NATS JetStream endpoint                   |
| `NOTIFICATION_CHANNEL_MAP` | values.yaml | Channel name → Discord channel ID mapping |
| `GITHUB_TOKEN`             | 1Password   | For gist creation                         |

### Discord Bot Setup (Manual, One-Time)

1. Create application at Discord Developer Portal
2. Enable Gateway Intents (Message Content, Server Members)
3. Set bot permissions (Send Messages, Read History, Attach Files, Create Threads)
4. Store credentials in 1Password vault `k8s-homelab`
5. Invite bot to server with OAuth2 URL

## Error Handling

- Orchestrator unavailable → reply "Service temporarily unavailable"
- llama-cpp unavailable → same fallback message
- Job fails → reply with failure reason from orchestrator output
- NATS disconnection → reconnect with backoff (nats.js built-in)

## Future Extensions

- Add Slack adapter (Chat SDK swap)
- Conversational mode (AI-driven intent detection)
- Slash commands for common operations
- Thread-based conversations for long-running research

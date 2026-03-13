# Chat Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a multi-platform chat bot (Discord first) that routes owner mentions to the orchestrator for research jobs and everyone else to llama-cpp for immediate responses, with outbound notifications via NATS.

**Architecture:** TypeScript service using Chat SDK with Discord adapter. Long-running process with Gateway WebSocket. NATS JetStream for job state tracking and notification subscriptions. Deployed as standalone ArgoCD Application (like cluster-agents).

**Tech Stack:** TypeScript, Chat SDK (`chat` + `@chat-adapter/discord`), nats.js, Node.js 20, apko, Bazel (rules_js), Helm

**Design doc:** `docs/plans/2026-03-12-chat-bot-design.md`

---

### Task 1: Project Scaffolding

**Files:**

- Create: `projects/agent_platform/chat_bot/package.json`
- Create: `projects/agent_platform/chat_bot/tsconfig.json`
- Modify: `pnpm-workspace.yaml` (add workspace entry)

**Step 1: Create package.json**

```json
{
  "name": "@homelab/chat-bot",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node --import tsx src/index.ts",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "chat": "latest",
    "@chat-adapter/discord": "latest",
    "nats": "^2.29.0",
    "tsx": "^4.19.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^20.0.0"
  }
}
```

**Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*.ts"]
}
```

**Step 3: Add to pnpm workspace**

Add `projects/agent_platform/chat_bot` to the `packages` list in `pnpm-workspace.yaml`.

**Step 4: Install dependencies**

Run: `cd /tmp/claude-worktrees/<branch> && pnpm install`

**Step 5: Commit**

```bash
git add projects/agent_platform/chat_bot/package.json projects/agent_platform/chat_bot/tsconfig.json pnpm-workspace.yaml pnpm-lock.yaml
git commit -m "feat(chat-bot): scaffold TypeScript project with Chat SDK dependencies"
```

---

### Task 2: Config Module

**Files:**

- Create: `projects/agent_platform/chat_bot/src/config.ts`

**Step 1: Write config with required env var validation**

```typescript
function required(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`Missing required env var: ${key}`);
  return value;
}

function optional(key: string, fallback: string): string {
  return process.env[key] || fallback;
}

function parseChannelMap(raw: string): Map<string, string> {
  const map = new Map<string, string>();
  if (!raw) return map;
  for (const pair of raw.split(",")) {
    const [name, id] = pair.split(":");
    if (name && id) map.set(name.trim(), id.trim());
  }
  return map;
}

export function loadConfig() {
  return {
    discord: {
      botToken: required("DISCORD_BOT_TOKEN"),
      publicKey: required("DISCORD_PUBLIC_KEY"),
      applicationId: required("DISCORD_APPLICATION_ID"),
    },
    ownerDiscordUserId: required("OWNER_DISCORD_USER_ID"),
    orchestratorUrl: required("ORCHESTRATOR_URL"),
    llamaCppUrl: required("LLAMA_CPP_URL"),
    natsUrl: required("NATS_URL"),
    githubToken: required("GITHUB_TOKEN"),
    notificationChannelMap: parseChannelMap(
      optional("NOTIFICATION_CHANNEL_MAP", ""),
    ),
    httpPort: optional("HTTP_PORT", "8080"),
  } as const;
}

export type Config = ReturnType<typeof loadConfig>;
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/config.ts
git commit -m "feat(chat-bot): add config module with env var validation"
```

---

### Task 3: Orchestrator Client

**Files:**

- Create: `projects/agent_platform/chat_bot/src/orchestrator.ts`

Ref: `projects/agent_platform/orchestrator/api.go` for API shape.

**Step 1: Write orchestrator client**

```typescript
export interface Job {
  id: string;
  status: string;
  created_at: string;
}

export interface JobOutput {
  output: string;
  result?: {
    summary?: string;
  };
  status: string;
}

export class OrchestratorClient {
  constructor(private baseUrl: string) {}

  async submitJob(task: string): Promise<Job> {
    const res = await fetch(`${this.baseUrl}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, source: "discord" }),
    });
    if (!res.ok)
      throw new Error(`Orchestrator error: ${res.status} ${await res.text()}`);
    return res.json() as Promise<Job>;
  }

  async getJobOutput(jobId: string): Promise<JobOutput> {
    const res = await fetch(`${this.baseUrl}/jobs/${jobId}/output`);
    if (!res.ok) throw new Error(`Orchestrator error: ${res.status}`);
    return res.json() as Promise<JobOutput>;
  }
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/orchestrator.ts
git commit -m "feat(chat-bot): add orchestrator API client"
```

---

### Task 4: LLM Client

**Files:**

- Create: `projects/agent_platform/chat_bot/src/llm.ts`

llama-cpp serves an OpenAI-compatible API at `/v1/chat/completions`.

**Step 1: Write llama-cpp client**

```typescript
export class LlmClient {
  constructor(private baseUrl: string) {}

  async complete(prompt: string): Promise<string> {
    const res = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: prompt }],
      }),
    });
    if (!res.ok) throw new Error(`llama-cpp error: ${res.status}`);
    const data = (await res.json()) as {
      choices: Array<{ message: { content: string } }>;
    };
    return data.choices[0]?.message?.content ?? "(no response)";
  }
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/llm.ts
git commit -m "feat(chat-bot): add llama-cpp OpenAI-compatible client"
```

---

### Task 5: GitHub Gist Client

**Files:**

- Create: `projects/agent_platform/chat_bot/src/gist.ts`

**Step 1: Write gist creation client**

```typescript
export class GistClient {
  constructor(private token: string) {}

  async create(description: string, content: string): Promise<string> {
    const res = await fetch("https://api.github.com/gists", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        description,
        public: false,
        files: { "output.md": { content } },
      }),
    });
    if (!res.ok) throw new Error(`GitHub API error: ${res.status}`);
    const data = (await res.json()) as { html_url: string };
    return data.html_url;
  }
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/gist.ts
git commit -m "feat(chat-bot): add GitHub gist client for job output"
```

---

### Task 6: NATS Integration

**Files:**

- Create: `projects/agent_platform/chat_bot/src/nats.ts`

Ref: nats.js docs for JetStream KV and subscriptions.

**Step 1: Write NATS module**

```typescript
import {
  connect,
  type NatsConnection,
  type KV,
  type JetStreamClient,
  StringCodec,
} from "nats";

const sc = StringCodec();

export interface NotificationMessage {
  title: string;
  body: string;
  severity: "info" | "warning" | "critical";
  source: string;
  metadata?: Record<string, unknown>;
}

export interface MessageRef {
  channelId: string;
  messageId: string;
}

export class NatsClient {
  private nc!: NatsConnection;
  private js!: JetStreamClient;
  private kv!: KV;

  constructor(private natsUrl: string) {}

  async connect(): Promise<void> {
    this.nc = await connect({ servers: this.natsUrl });
    this.js = this.nc.jetstream();
    this.kv = await this.js.views.kv("chat-bot-state");
  }

  async storeMessageRef(jobId: string, ref: MessageRef): Promise<void> {
    await this.kv.put(jobId, sc.encode(JSON.stringify(ref)));
  }

  async getMessageRef(jobId: string): Promise<MessageRef | null> {
    const entry = await this.kv.get(jobId);
    if (!entry?.value) return null;
    return JSON.parse(sc.decode(entry.value)) as MessageRef;
  }

  async subscribeNotifications(
    handler: (subject: string, msg: NotificationMessage) => Promise<void>,
  ): Promise<void> {
    const sub = this.nc.subscribe("notifications.discord.>");
    for await (const msg of sub) {
      try {
        const notification = JSON.parse(
          sc.decode(msg.data),
        ) as NotificationMessage;
        await handler(msg.subject, notification);
      } catch (err) {
        console.error("Failed to process notification", err);
      }
    }
  }

  async close(): Promise<void> {
    await this.nc.close();
  }
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/nats.ts
git commit -m "feat(chat-bot): add NATS client for state and notifications"
```

---

### Task 7: Message Handlers

**Files:**

- Create: `projects/agent_platform/chat_bot/src/handlers.ts`

This is the core routing logic. Ref: Chat SDK `onNewMention` handler, `thread.post()` for replies, `message.author.userId` for identification.

**Step 1: Write mention handler**

```typescript
import type { Thread, Message } from "chat";
import type { Config } from "./config.js";
import type { OrchestratorClient } from "./orchestrator.js";
import type { LlmClient } from "./llm.js";
import type { GistClient } from "./gist.js";
import type { NatsClient } from "./nats.js";

export interface HandlerDeps {
  config: Config;
  orchestrator: OrchestratorClient;
  llm: LlmClient;
  gist: GistClient;
  nats: NatsClient;
}

export function createMentionHandler(deps: HandlerDeps) {
  return async (thread: Thread, message: Message) => {
    const text = message.text?.trim();
    if (!text) return;

    const isOwner = message.author?.userId === deps.config.ownerDiscordUserId;

    if (isOwner) {
      await handleOwnerRequest(thread, text, deps);
    } else {
      await handlePublicRequest(thread, text, deps);
    }
  };
}

async function handleOwnerRequest(
  thread: Thread,
  text: string,
  deps: HandlerDeps,
): Promise<void> {
  await thread.post("Researching...");

  try {
    const job = await deps.orchestrator.submitJob(text);

    // Store message ref for reply when job completes
    // Note: thread context is used for polling, not NATS callback
    await deps.nats.storeMessageRef(job.id, {
      channelId: "", // Will be populated from thread context
      messageId: "",
    });

    // Poll for job completion
    pollForResult(thread, job.id, deps);
  } catch (err) {
    await thread.post(
      "Service temporarily unavailable. Please try again later.",
    );
    console.error("Failed to submit job", err);
  }
}

async function handlePublicRequest(
  thread: Thread,
  text: string,
  deps: HandlerDeps,
): Promise<void> {
  try {
    await thread.startTyping();
    const response = await deps.llm.complete(text);
    await thread.post(response);
  } catch (err) {
    await thread.post(
      "Service temporarily unavailable. Please try again later.",
    );
    console.error("Failed to get LLM response", err);
  }
}

async function pollForResult(
  thread: Thread,
  jobId: string,
  deps: HandlerDeps,
): Promise<void> {
  const maxAttempts = 120; // 10 minutes at 5s intervals
  const interval = 5000;

  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, interval));

    try {
      const output = await deps.orchestrator.getJobOutput(jobId);

      if (output.status === "SUCCEEDED" || output.status === "FAILED") {
        const summary =
          output.result?.summary ?? output.output.slice(0, 500) ?? "No output";
        let reply = `**Job ${jobId}** — ${output.status}\n\n${summary}`;

        if (output.output && output.output.length > 500) {
          try {
            const gistUrl = await deps.gist.create(
              `Research: ${jobId}`,
              output.output,
            );
            reply += `\n\n**Full output:** ${gistUrl}`;
          } catch (err) {
            console.error("Failed to create gist", err);
          }
        }

        await thread.post(reply);
        return;
      }

      if (output.status === "CANCELLED") {
        await thread.post(`**Job ${jobId}** was cancelled.`);
        return;
      }
    } catch (err) {
      console.error("Failed to poll job", err);
    }
  }

  await thread.post(`**Job ${jobId}** timed out waiting for result.`);
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/handlers.ts
git commit -m "feat(chat-bot): add mention handler with owner/public routing"
```

---

### Task 8: Entry Point

**Files:**

- Create: `projects/agent_platform/chat_bot/src/index.ts`

**Step 1: Write main entry point**

Wire up Chat SDK, Discord adapter, NATS subscriber, and health check server.

```typescript
import { Chat } from "chat";
import { createDiscordAdapter } from "@chat-adapter/discord";
import http from "node:http";
import { loadConfig } from "./config.js";
import { OrchestratorClient } from "./orchestrator.js";
import { LlmClient } from "./llm.js";
import { GistClient } from "./gist.js";
import { NatsClient } from "./nats.js";
import { createMentionHandler } from "./handlers.js";

async function main() {
  const config = loadConfig();

  // Initialize clients
  const orchestrator = new OrchestratorClient(config.orchestratorUrl);
  const llm = new LlmClient(config.llamaCppUrl);
  const gist = new GistClient(config.githubToken);
  const nats = new NatsClient(config.natsUrl);

  await nats.connect();
  console.log("Connected to NATS");

  // Initialize Chat SDK with Discord adapter
  const bot = new Chat({
    userName: "homelab-bot",
    adapters: {
      discord: createDiscordAdapter(),
    },
  });

  const deps = { config, orchestrator, llm, gist, nats };

  // Handle mentions
  bot.onNewMention(createMentionHandler(deps));

  // Subscribe to outbound notifications
  const discordAdapter = bot.getAdapter("discord");
  nats.subscribeNotifications(async (subject, notification) => {
    const channelName = subject.split(".").pop() ?? "default";
    const channelId =
      config.notificationChannelMap.get(channelName) ??
      config.notificationChannelMap.get("default");

    if (!channelId) {
      console.warn(`No channel mapping for: ${channelName}`);
      return;
    }

    const severityEmoji =
      notification.severity === "critical"
        ? "🚨"
        : notification.severity === "warning"
          ? "⚠️"
          : "ℹ️";

    const channel = bot.channel(channelId, "discord");
    await channel.post(
      `${severityEmoji} **${notification.title}**\n${notification.body}\n_Source: ${notification.source}_`,
    );
  });

  await bot.initialize();
  console.log("Chat bot initialized");

  // Health check server
  const server = http.createServer((req, res) => {
    if (req.url === "/health") {
      res.writeHead(200);
      res.end("ok");
    } else {
      res.writeHead(404);
      res.end();
    }
  });

  server.listen(Number(config.httpPort), () => {
    console.log(`Health check listening on :${config.httpPort}`);
  });

  // Graceful shutdown
  const shutdown = async () => {
    console.log("Shutting down...");
    await bot.shutdown();
    await nats.close();
    server.close();
    process.exit(0);
  };

  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch((err) => {
  console.error("Fatal error", err);
  process.exit(1);
});
```

> **Note:** The exact Chat SDK API (`bot.channel()`, `bot.getAdapter()`, etc.) may differ — consult the latest Chat SDK docs during implementation and adjust accordingly. The SDK is in beta.

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/src/index.ts
git commit -m "feat(chat-bot): add entry point with Chat SDK, NATS, and health check"
```

---

### Task 9: Container Image

**Files:**

- Create: `projects/agent_platform/chat_bot/image/apko.yaml`

Ref: `projects/ships/frontend/apko.yaml` for the Bun/Node pattern.

**Step 1: Write apko config**

```yaml
contents:
  repositories:
    - https://packages.wolfi.dev/os
  keyring:
    - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
  packages:
    - nodejs-20
    - ca-certificates-bundle

archs:
  - x86_64
  - aarch64

cmd: node --import tsx /app/src/index.ts

work-dir: /app

accounts:
  users:
    - username: nonroot
      uid: 65532
      gid: 65532
  groups:
    - groupname: nonroot
      gid: 65532
  run-as: 65532

paths:
  - path: /app
    type: directory
    uid: 65532
    gid: 65532
    permissions: 0o755

environment:
  NODE_ENV: production
  HTTP_PORT: "8080"
```

**Step 2: Commit**

```bash
git add projects/agent_platform/chat_bot/image/apko.yaml
git commit -m "feat(chat-bot): add apko container image config"
```

---

### Task 10: Bazel BUILD File

**Files:**

- Create: `projects/agent_platform/chat_bot/BUILD`

Ref: `projects/ships/frontend/BUILD` for the pkg_tar + apko_image pattern.

**Step 1: Write BUILD file**

Package the TypeScript source + node_modules into the container. The exact Bazel rules depend on how the pnpm workspace resolves — `format` (gazelle) will update this.

```starlark
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Package source files
pkg_tar(
    name = "src_tar",
    srcs = glob(["src/**/*.ts"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/src",
    strip_prefix = "src",
)

# Package package.json and tsconfig for tsx runtime
pkg_tar(
    name = "config_tar",
    srcs = [
        "package.json",
        "tsconfig.json",
    ],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app",
)

apko_image(
    name = "image",
    config = "image/apko.yaml",
    contents = "@chat_bot_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/agent-platform/chat-bot",
    tars = [
        ":src_tar",
        ":config_tar",
    ],
)
```

> **Note:** node_modules packaging needs investigation during implementation. Options: (a) bundle with esbuild into a single JS file (preferred — eliminates node_modules in container), (b) include node_modules tar. If bundling, replace tsx runtime with direct `node /app/dist/index.js`. Run `format` to let gazelle fix BUILD details.

**Step 2: Register apko lock in MODULE.bazel**

Add to `MODULE.bazel`:

```starlark
apko.translate_lock(
    name = "chat_bot_lock",
    lock = "//projects/agent_platform/chat_bot/image:apko.lock.json",
)
```

**Step 3: Generate apko lock file**

Run: `apko lock image/apko.yaml` (or let CI generate it)

**Step 4: Run format**

Run: `format` to regenerate BUILD files and fix any gazelle issues.

**Step 5: Commit**

```bash
git add projects/agent_platform/chat_bot/BUILD projects/agent_platform/chat_bot/image/ MODULE.bazel
git commit -m "build(chat-bot): add Bazel BUILD and apko image config"
```

---

### Task 11: Helm Chart

**Files:**

- Create: `projects/agent_platform/chat_bot/deploy/Chart.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/values.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/templates/_helpers.tpl`
- Create: `projects/agent_platform/chat_bot/deploy/templates/deployment.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/templates/service.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/templates/serviceaccount.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/templates/onepassworditem.yaml`

Ref: `projects/agent_platform/cluster_agents/deploy/` for the exact pattern.

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: chat-bot
description: Multi-platform chat bot for homelab cluster interaction
type: application
version: 0.1.0
appVersion: "0.1.0"
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

```yaml
replicaCount: 1

image:
  repository: ghcr.io/jomcgi/homelab/projects/agent-platform/chat-bot
  tag: main
  pullPolicy: IfNotPresent

imagePullSecret:
  enabled: false
  create: true
  onepassword:
    itemPath: "vaults/k8s-homelab/items/ghcr-read-permissions"

nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations: {}

podSecurityContext:
  seccompProfile:
    type: RuntimeDefault

securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: 8080

resources:
  requests:
    cpu: 10m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 256Mi

config:
  ownerDiscordUserId: ""
  orchestratorUrl: "http://agent-platform-agent-orchestrator.agent-platform.svc.cluster.local:8080"
  llamaCppUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"
  natsUrl: "nats://agent-platform-nats.agent-platform.svc.cluster.local:4222"
  notificationChannelMap: ""
  httpPort: "8080"

secrets:
  discordCredentials:
    onepassword:
      itemPath: "vaults/k8s-homelab/items/discord-bot-credentials"
  githubToken:
    onepassword:
      itemPath: "vaults/k8s-homelab/items/agent-secrets"

nodeSelector: {}
tolerations: []
affinity: {}
```

**Step 3: Create templates**

Create `_helpers.tpl` with standard name/label helpers (copy from cluster-agents, rename `cluster-agents` → `chat-bot`).

Create `deployment.yaml` following the cluster-agents pattern:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "chat-bot.fullname" . }}
  labels:
    {{- include "chat-bot.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      {{- include "chat-bot.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "chat-bot.selectorLabels" . | nindent 8 }}
    spec:
      {{- if .Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- end }}
      serviceAccountName: {{ include "chat-bot.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
      - name: {{ .Chart.Name }}
        securityContext:
          {{- toYaml .Values.securityContext | nindent 10 }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: {{ .Values.service.port }}
          protocol: TCP
        env:
        - name: DISCORD_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: discord-bot-credentials
              key: DISCORD_BOT_TOKEN
        - name: DISCORD_PUBLIC_KEY
          valueFrom:
            secretKeyRef:
              name: discord-bot-credentials
              key: DISCORD_PUBLIC_KEY
        - name: DISCORD_APPLICATION_ID
          valueFrom:
            secretKeyRef:
              name: discord-bot-credentials
              key: DISCORD_APPLICATION_ID
        - name: OWNER_DISCORD_USER_ID
          value: {{ .Values.config.ownerDiscordUserId | quote }}
        - name: ORCHESTRATOR_URL
          value: {{ .Values.config.orchestratorUrl | quote }}
        - name: LLAMA_CPP_URL
          value: {{ .Values.config.llamaCppUrl | quote }}
        - name: NATS_URL
          value: {{ .Values.config.natsUrl | quote }}
        - name: NOTIFICATION_CHANNEL_MAP
          value: {{ .Values.config.notificationChannelMap | quote }}
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: agent-secrets
              key: GITHUB_TOKEN
        - name: HTTP_PORT
          value: {{ .Values.config.httpPort | quote }}
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

Create `service.yaml`, `serviceaccount.yaml`, `onepassworditem.yaml` — standard Helm templates matching cluster-agents.

The `onepassworditem.yaml` should create both secrets:

```yaml
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: discord-bot-credentials
  labels: { { - include "chat-bot.labels" . | nindent 4 } }
spec:
  itemPath:
    { { .Values.secrets.discordCredentials.onepassword.itemPath | quote } }
---
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: agent-secrets
  labels: { { - include "chat-bot.labels" . | nindent 4 } }
spec:
  itemPath: { { .Values.secrets.githubToken.onepassword.itemPath | quote } }
```

**Step 4: Validate chart renders**

Run: `helm template chat-bot projects/agent_platform/chat_bot/deploy/ -f projects/agent_platform/chat_bot/deploy/values.yaml`

Verify: all resources render without errors.

**Step 5: Commit**

```bash
git add projects/agent_platform/chat_bot/deploy/
git commit -m "feat(chat-bot): add Helm chart with deployment, secrets, and service"
```

---

### Task 12: ArgoCD Application

**Files:**

- Create: `projects/agent_platform/chat_bot/deploy/application.yaml`
- Create: `projects/agent_platform/chat_bot/deploy/kustomization.yaml`

Ref: `projects/agent_platform/cluster_agents/deploy/application.yaml`

**Step 1: Create application.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: chat-bot
  namespace: argocd
spec:
  project: default
  source:
    repoURL: ghcr.io/jomcgi/homelab/charts
    chart: chat-bot
    targetRevision: 0.1.0
    helm:
      releaseName: chat-bot
      valuesObject:
        imagePullSecret:
          enabled: true
        config:
          ownerDiscordUserId: "" # Set after Discord bot creation
          notificationChannelMap: "" # Set after Discord bot creation
  destination:
    server: https://kubernetes.default.svc
    namespace: chat-bot
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**Step 2: Create kustomization.yaml**

```yaml
resources:
  - application.yaml
```

**Step 3: Run format**

Run: `format` to ensure the new kustomization is picked up by the home-cluster root.

**Step 4: Commit**

```bash
git add projects/agent_platform/chat_bot/deploy/application.yaml projects/agent_platform/chat_bot/deploy/kustomization.yaml
git commit -m "feat(chat-bot): add ArgoCD Application and kustomization"
```

---

### Task 13: Helm Chart BUILD File

**Files:**

- Create: `projects/agent_platform/chat_bot/deploy/BUILD`

Ref: `projects/agent_platform/cluster_agents/deploy/BUILD` (or let `format`/gazelle generate it).

**Step 1: Create BUILD file for chart publishing**

```starlark
load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/agent_platform/chat_bot:image.info",
    },
    publish = True,
)
```

**Step 2: Run format**

Run: `format` to let gazelle fix up any missing details.

**Step 3: Commit**

```bash
git add projects/agent_platform/chat_bot/deploy/BUILD
git commit -m "build(chat-bot): add Helm chart Bazel BUILD for CI publishing"
```

---

### Task 14: Cluster-Agents NotificationPublisher

**Files:**

- Create: `projects/agent_platform/cluster_agents/notification.go`
- Create: `projects/agent_platform/cluster_agents/notification_test.go`
- Modify: `projects/agent_platform/cluster_agents/main.go` (wire in publisher)

This adds the Go side for cluster-agents to publish notifications to NATS.

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
)

func startTestNATS(t *testing.T) (*server.Server, string) {
	t.Helper()
	opts := &server.Options{Port: -1, JetStream: true}
	ns, err := server.NewServer(opts)
	if err != nil {
		t.Fatal(err)
	}
	ns.Start()
	t.Cleanup(ns.Shutdown)
	if !ns.ReadyForConnections(2 * time.Second) {
		t.Fatal("nats not ready")
	}
	return ns, ns.ClientURL()
}

func TestNotificationPublisher(t *testing.T) {
	_, url := startTestNATS(t)

	nc, err := nats.Connect(url)
	if err != nil {
		t.Fatal(err)
	}
	defer nc.Close()

	publisher := NewNotificationPublisher(nc)

	// Subscribe before publishing
	sub, err := nc.SubscribeSync("notifications.discord.alerts")
	if err != nil {
		t.Fatal(err)
	}

	err = publisher.Notify(context.Background(), "alerts", NotificationMessage{
		Title:    "Test Alert",
		Body:     "Something happened",
		Severity: "warning",
		Source:   "test",
	})
	if err != nil {
		t.Fatal(err)
	}

	msg, err := sub.NextMsg(2 * time.Second)
	if err != nil {
		t.Fatal(err)
	}

	var got NotificationMessage
	if err := json.Unmarshal(msg.Data, &got); err != nil {
		t.Fatal(err)
	}

	if got.Title != "Test Alert" {
		t.Errorf("got title %q, want %q", got.Title, "Test Alert")
	}
}
```

**Step 2: Write the implementation**

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/nats-io/nats.go"
)

type NotificationMessage struct {
	Title    string         `json:"title"`
	Body     string         `json:"body"`
	Severity string         `json:"severity"`
	Source   string         `json:"source"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

type NotificationPublisher struct {
	nc *nats.Conn
}

func NewNotificationPublisher(nc *nats.Conn) *NotificationPublisher {
	return &NotificationPublisher{nc: nc}
}

func (p *NotificationPublisher) Notify(ctx context.Context, channel string, msg NotificationMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("marshal notification: %w", err)
	}
	subject := fmt.Sprintf("notifications.discord.%s", channel)
	return p.nc.Publish(subject, data)
}
```

**Step 3: Wire into main.go**

Add NATS connection + publisher to `main.go`:

```go
// Add env var
natsURL := envOr("NATS_URL", "nats://agent-platform-nats.agent-platform.svc.cluster.local:4222")

// Connect to NATS
nc, err := nats.Connect(natsURL)
if err != nil {
    slog.Error("failed to connect to NATS", "error", err)
    os.Exit(1)
}
defer nc.Close()

publisher := NewNotificationPublisher(nc)
```

> **Important:** Do NOT hardcode the NATS URL as a default in code — use `envOr("NATS_URL", "")` and configure in values.yaml per repo convention. The example above shows the value that goes in `values.yaml`, not in Go code.

Then pass `publisher` to agents that should send notifications (e.g., patrol agent for critical findings). This is additive — existing agents continue to work unchanged.

**Step 4: Add NATS config to cluster-agents values.yaml**

Add to `config:` section:

```yaml
natsUrl: "nats://agent-platform-nats.agent-platform.svc.cluster.local:4222"
```

Add env var to deployment template.

**Step 5: Bump cluster-agents chart version**

Update `Chart.yaml` version (e.g., `0.3.4` → `0.4.0`).

**Step 6: Run format**

Run: `format` to update BUILD files with new Go dependency.

**Step 7: Commit**

```bash
git add projects/agent_platform/cluster_agents/notification.go projects/agent_platform/cluster_agents/notification_test.go projects/agent_platform/cluster_agents/main.go projects/agent_platform/cluster_agents/deploy/
git commit -m "feat(cluster-agents): add NATS notification publisher for Discord"
```

---

### Task 15: Discord Bot Setup (Manual)

This task is done outside the repo — no code changes.

**Step 1: Create Discord Application**

Go to Discord Developer Portal → New Application → name it "Homelab Bot"

**Step 2: Configure bot**

- Enable "Message Content Intent" under Privileged Gateway Intents
- Set bot permissions: Send Messages, Send Messages in Threads, Read Message History, Attach Files, Add Reactions

**Step 3: Store secrets in 1Password**

Create item `discord-bot-credentials` in vault `k8s-homelab` with fields:

- `DISCORD_BOT_TOKEN`
- `DISCORD_PUBLIC_KEY`
- `DISCORD_APPLICATION_ID`

**Step 4: Invite bot to server**

Generate OAuth2 URL with `bot` scope and the permissions above. Invite to your Discord server.

**Step 5: Update ArgoCD Application**

Set `ownerDiscordUserId` and `notificationChannelMap` in `application.yaml` valuesObject.

**Step 6: Commit the config update**

```bash
git add projects/agent_platform/chat_bot/deploy/application.yaml
git commit -m "feat(chat-bot): configure Discord user and channel mappings"
```

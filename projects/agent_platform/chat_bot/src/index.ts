import { createServer } from "node:http";
import { Chat, type StateAdapter, type Lock } from "chat";
import { createDiscordAdapter } from "@chat-adapter/discord";
import { loadConfig } from "./config.js";
import { OrchestratorClient } from "./orchestrator.js";
import { LlmClient } from "./llm.js";
import { GistClient } from "./gist.js";
import { NatsClient, type NotificationMessage } from "./nats.js";
import { createMentionHandler } from "./handlers.js";

/**
 * Minimal in-memory StateAdapter for the Chat SDK.
 * Sufficient for a single-instance bot that does not need persistent
 * subscriptions or distributed locking.
 */
class MemoryStateAdapter implements StateAdapter {
  private store = new Map<string, { value: unknown; expiresAt?: number }>();
  private lists = new Map<string, unknown[]>();
  private subscriptions = new Set<string>();
  private locks = new Map<string, { token: string; expiresAt: number }>();

  async connect(): Promise<void> {}
  async disconnect(): Promise<void> {}

  async get<T = unknown>(key: string): Promise<T | null> {
    const entry = this.store.get(key);
    if (!entry) return null;
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return null;
    }
    return entry.value as T;
  }

  async set(key: string, value: unknown, ttlMs?: number): Promise<void> {
    this.store.set(key, {
      value,
      expiresAt: ttlMs ? Date.now() + ttlMs : undefined,
    });
  }

  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }

  async setIfNotExists(
    key: string,
    value: unknown,
    ttlMs?: number,
  ): Promise<boolean> {
    const existing = await this.get(key);
    if (existing !== null) return false;
    await this.set(key, value, ttlMs);
    return true;
  }

  async appendToList(
    key: string,
    value: unknown,
    options?: { maxLength?: number; ttlMs?: number },
  ): Promise<void> {
    const list = this.lists.get(key) ?? [];
    list.push(value);
    if (options?.maxLength && list.length > options.maxLength) {
      list.splice(0, list.length - options.maxLength);
    }
    this.lists.set(key, list);
  }

  async getList<T = unknown>(key: string): Promise<T[]> {
    return (this.lists.get(key) ?? []) as T[];
  }

  async subscribe(threadId: string): Promise<void> {
    this.subscriptions.add(threadId);
  }

  async unsubscribe(threadId: string): Promise<void> {
    this.subscriptions.delete(threadId);
  }

  async isSubscribed(threadId: string): Promise<boolean> {
    return this.subscriptions.has(threadId);
  }

  async acquireLock(threadId: string, ttlMs: number): Promise<Lock | null> {
    const existing = this.locks.get(threadId);
    if (existing && Date.now() < existing.expiresAt) return null;
    const lock: Lock = {
      threadId,
      token: crypto.randomUUID(),
      expiresAt: Date.now() + ttlMs,
    };
    this.locks.set(threadId, lock);
    return lock;
  }

  async releaseLock(lock: Lock): Promise<void> {
    const existing = this.locks.get(lock.threadId);
    if (existing?.token === lock.token) {
      this.locks.delete(lock.threadId);
    }
  }

  async extendLock(lock: Lock, ttlMs: number): Promise<boolean> {
    const existing = this.locks.get(lock.threadId);
    if (existing?.token !== lock.token) return false;
    existing.expiresAt = Date.now() + ttlMs;
    return true;
  }

  async forceReleaseLock(threadId: string): Promise<void> {
    this.locks.delete(threadId);
  }
}

function formatNotification(notification: NotificationMessage): string {
  const severityEmoji: Record<string, string> = {
    critical: "\u{1F6A8}",
    warning: "\u26A0\uFE0F",
    info: "\u2139\uFE0F",
  };

  const prefix = severityEmoji[notification.severity] ?? "";
  const parts = [
    `${prefix} **${notification.title}**`,
    notification.body,
    `_Source: ${notification.source}_`,
  ];

  return parts.join("\n\n");
}

async function main(): Promise<void> {
  const config = loadConfig();

  // Initialize clients
  const orchestrator = new OrchestratorClient(config.orchestratorUrl);
  const llm = new LlmClient(config.llamaCppUrl);
  const gist = new GistClient(config.githubToken);
  const nats = new NatsClient(config.natsUrl);

  await nats.connect();
  console.log("Connected to NATS");

  // Create Chat SDK instance with Discord adapter
  const discord = createDiscordAdapter({
    botToken: config.discord.botToken,
    publicKey: config.discord.publicKey,
    applicationId: config.discord.applicationId,
  });

  const bot = new Chat({
    userName: "chat-bot",
    adapters: { discord },
    state: new MemoryStateAdapter(),
  });

  // Register mention handler
  const handler = createMentionHandler({
    config,
    orchestrator,
    llm,
    gist,
    nats,
  });
  bot.onNewMention(handler);

  // Subscribe to NATS notifications and forward to Discord channels
  nats
    .subscribeNotifications(async (subject, notification) => {
      // Subject format: notifications.discord.<channelName>
      const parts = subject.split(".");
      const channelName = parts[parts.length - 1];
      const channelId = config.notificationChannelMap.get(channelName ?? "");
      if (!channelId) {
        console.warn(`No channel mapping for notification subject: ${subject}`);
        return;
      }

      const text = formatNotification(notification);
      const channel = bot.channel(`discord:_:${channelId}`);
      await channel.post(text);
    })
    .catch((err) => {
      console.error("Notification subscription error:", err);
    });

  // Initialize the bot (sets up HTTP interactions)
  await bot.initialize();
  console.log("Chat bot initialized");

  // Start Gateway WebSocket for receiving messages and mentions.
  // Without this, only slash commands/button clicks work (HTTP interactions).
  const abortController = new AbortController();
  const gatewayLoop = async () => {
    while (!abortController.signal.aborted) {
      try {
        console.log("Starting Discord Gateway listener...");
        await discord.startGatewayListener(
          { waitUntil: (task) => task },
          24 * 60 * 60 * 1000, // 24 hours
          abortController.signal,
        );
      } catch (err) {
        if (abortController.signal.aborted) break;
        console.error("Gateway listener error, reconnecting in 5s:", err);
        await new Promise((r) => setTimeout(r, 5000));
      }
    }
  };
  gatewayLoop();

  // Start HTTP health check server
  const port = parseInt(config.httpPort, 10);
  const server = createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
  });

  server.listen(port, () => {
    console.log(`Health check server listening on port ${port}`);
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    console.log(`Received ${signal}, shutting down...`);
    abortController.abort();
    server.close();
    await bot.shutdown();
    await nats.close();
    console.log("Shutdown complete");
    process.exit(0);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});

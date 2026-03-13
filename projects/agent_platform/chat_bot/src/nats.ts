import {
  connect,
  type NatsConnection,
  type KV,
  type JetStreamClient,
} from "nats";

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
    await this.kv.put(jobId, JSON.stringify(ref));
  }

  async getMessageRef(jobId: string): Promise<MessageRef | null> {
    const entry = await this.kv.get(jobId);
    if (!entry?.value) return null;
    return entry.json<MessageRef>();
  }

  async subscribeNotifications(
    handler: (subject: string, msg: NotificationMessage) => Promise<void>,
  ): Promise<void> {
    const sub = this.nc.subscribe("notifications.discord.>");
    for await (const msg of sub) {
      try {
        const notification = msg.json<NotificationMessage>();
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

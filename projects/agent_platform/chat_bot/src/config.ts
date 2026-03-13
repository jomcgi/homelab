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

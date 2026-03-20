import type { Thread, Message, MentionHandler } from "chat";
import type { Config } from "./config.js";
import type { OrchestratorClient } from "./orchestrator.js";
import type { LlmClient } from "./llm.js";
import type { NatsClient } from "./nats.js";

export interface HandlerDeps {
  config: Config;
  orchestrator: OrchestratorClient;
  llm: LlmClient;
  nats: NatsClient;
}

const POLL_INTERVAL_MS = 5_000;
const MAX_STALE_POLLS = 120; // give up after 10 minutes of no reachable status

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function truncate(text: string, max: number): string {
  if (!text || text.length <= max) return text;
  return text.slice(0, max) + "\n\n…(truncated)";
}

export function createMentionHandler(deps: HandlerDeps): MentionHandler {
  return async (thread: Thread, message: Message) => {
    const text = message.text?.trim();
    if (!text) return;

    const isOwner = message.author?.userId === deps.config.ownerDiscordUserId;

    try {
      if (isOwner) {
        await handleOwnerRequest(thread, text, deps);
      } else {
        await handlePublicRequest(thread, text, deps);
      }
    } catch (err) {
      console.error("Handler error:", err);
      try {
        await thread.post(
          "Service temporarily unavailable. Please try again later.",
        );
      } catch (replyErr) {
        console.error("Failed to send error reply:", replyErr);
      }
    }
  };
}

async function handleOwnerRequest(
  thread: Thread,
  text: string,
  deps: HandlerDeps,
): Promise<void> {
  await thread.startTyping();
  const ack = await thread.post("Researching...");

  const job = await deps.orchestrator.submitJob(text);

  await deps.nats.storeMessageRef(job.id, {
    channelId: thread.id,
    messageId: ack.id,
  });

  await pollForResult(thread, job.id, deps);
}

async function handlePublicRequest(
  thread: Thread,
  text: string,
  deps: HandlerDeps,
): Promise<void> {
  await thread.startTyping();
  const reply = await deps.llm.complete(text);
  await thread.post(reply);
}

async function pollForResult(
  thread: Thread,
  jobId: string,
  deps: HandlerDeps,
): Promise<void> {
  let stalePollCount = 0;

  while (stalePollCount < MAX_STALE_POLLS) {
    await sleep(POLL_INTERVAL_MS);

    let output;
    try {
      output = await deps.orchestrator.getJobOutput(jobId);
    } catch {
      // 404 = no attempts yet, count toward stale timeout
      stalePollCount++;
      continue;
    }

    // Job is still active — reset stale counter and keep polling.
    if (output.status === "PENDING" || output.status === "RUNNING") {
      stalePollCount = 0;
      continue;
    }

    if (output.status === "SUCCEEDED") {
      // Prefer reply (user-facing answer) over summary (internal tracking).
      const message =
        (output.result?.reply ??
          output.result?.summary ??
          truncate(output.output, 1800)) ||
        "Job completed.";
      const url = output.result?.url;
      const reply = url ? `${message}\n\n${url}` : message;
      await thread.post(reply);
      return;
    }

    // Terminal failure (FAILED or CANCELLED)
    await thread.post(`Job failed: ${output.output || "unknown error"}`);
    return;
  }

  await thread.post(
    `Job ${jobId} timed out after ${(MAX_STALE_POLLS * POLL_INTERVAL_MS) / 60_000} minutes of inactivity. Check status manually.`,
  );
}

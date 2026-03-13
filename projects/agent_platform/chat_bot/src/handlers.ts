import type { Thread, Message, MentionHandler } from "chat";
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

const POLL_INTERVAL_MS = 5_000;
const MAX_POLL_ATTEMPTS = 120; // 10 minutes at 5s intervals
const GIST_THRESHOLD = 500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
    await sleep(POLL_INTERVAL_MS);

    const output = await deps.orchestrator.getJobOutput(jobId);

    if (output.status === "completed") {
      const summary = output.result?.summary ?? output.output;
      const fullOutput = output.output;

      if (fullOutput.length > GIST_THRESHOLD) {
        const gistUrl = await deps.gist.create(
          `Job ${jobId} output`,
          fullOutput,
        );
        await thread.post(`${summary}\n\nFull output: ${gistUrl}`);
      } else {
        await thread.post(summary);
      }
      return;
    }

    if (output.status === "failed") {
      await thread.post(`Job failed: ${output.output || "unknown error"}`);
      return;
    }
  }

  await thread.post(
    `Job ${jobId} timed out after ${(MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS) / 60_000} minutes. Check status manually.`,
  );
}

// ─── Condition config (static) ───────────────────────────────────────────────

export const CONDITIONS = ["always", "on success", "on failure"];

export const CONDITION_STYLES = {
  always: {
    className: "cond-always",
    color: "#6b7280",
    border: "#e5e7eb",
    bg: "transparent",
  },
  "on success": {
    className: "cond-success",
    color: "#065f46",
    border: "#6ee7b7",
    bg: "rgba(209,250,229,0.12)",
  },
  "on failure": {
    className: "cond-failure",
    color: "#991b1b",
    border: "#fca5a5",
    bg: "rgba(254,226,226,0.12)",
  },
};

// ─── Inference config ────────────────────────────────────────────────────────

// Points at your local llama-cpp instance. The endpoint should accept
// OpenAI-compatible /v1/chat/completions with response_format for constrained
// JSON output. Adjust the model string to whatever's loaded.
export const INFERENCE_URL =
  import.meta.env.VITE_INFERENCE_URL ||
  "http://localhost:8080/v1/chat/completions";

export const INFERENCE_MODEL =
  import.meta.env.VITE_INFERENCE_MODEL || "qwen3.5-38b";

// ─── Dynamic builders (depend on fetched agent list) ─────────────────────────

// JSON schema for constrained decoding. llama-cpp will use this as a GBNF
// grammar to guarantee valid output structure.
export function buildPipelineSchema(agents) {
  return {
    type: "object",
    required: ["steps"],
    properties: {
      steps: {
        type: "array",
        minItems: 1,
        maxItems: 5,
        items: {
          type: "object",
          required: ["agent", "task", "condition"],
          properties: {
            agent: {
              type: "string",
              enum: agents.map((a) => a.id),
            },
            task: { type: "string" },
            condition: {
              type: "string",
              enum: ["always", "on success", "on failure"],
            },
          },
        },
      },
    },
  };
}

export function buildSystemPrompt(agents) {
  return `You are a pipeline planner for an agent orchestrator. Decompose the user's task into a sequence of agent steps.

Available agents:
${agents.map((a) => `- ${a.id}: ${a.desc}`).join("\n")}

Return ONLY valid JSON matching this schema:
{"steps": [{"agent": "agent-id", "task": "specific sub-task", "condition": "always|on success|on failure"}]}

Rules:
- First step condition is always "always"
- "if it fails" → "on failure", "if successful" → "on success", default "always"
- Extract a specific sub-task for each step from the prompt
- If user mentions @tool:X use that agent; if @profile:X mention it in the first step's task
- 2–5 steps. Don't over-split.`;
}

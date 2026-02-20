/**
 * Export conversation messages as formatted Markdown.
 *
 * Reuses the same turn-grouping logic as TranscriptView.jsx so the
 * exported document mirrors the UI's visual structure.
 */

function groupMessages(messages) {
  const groups = [];
  let cur = null;
  messages.forEach((m) => {
    if (m.role === "voice") {
      if (cur) groups.push(cur);
      cur = { voice: m, steps: [], result: null, summary: null, approval: null };
    } else if (m.role === "claude") {
      if (!cur) cur = { voice: null, steps: [], result: null, summary: null, approval: null };
      if (m.status === "thinking" || m.status === "tool") cur.steps.push(m);
      else if (m.status === "approval") cur.approval = m;
      else if (m.status === "done") cur.result = m;
    } else if (m.role === "gemini") {
      if (cur) { cur.summary = m; groups.push(cur); cur = null; }
    }
  });
  if (cur) groups.push(cur);
  return groups;
}

function formatToolStep(text) {
  // Tool text from the backend looks like "Read: /path/to/file" or "Run: cmd"
  const m = text?.match(/^(\w+):\s*(.*)$/);
  if (m) return `**${m[1]}** \`${m[2]}\``;
  return text || "(unknown step)";
}

/**
 * Format an array of Bosun messages into a Markdown document.
 *
 * @param {Array} messages - The messages array (same shape as App.jsx state)
 * @param {string} [sessionId] - Optional session ID to include in header
 * @returns {string} Formatted markdown
 */
export function formatMarkdown(messages, sessionId) {
  const groups = groupMessages(messages);
  const lines = [];

  lines.push(`# Bosun Conversation Export`);
  if (sessionId) lines.push(`**Session:** \`${sessionId}\``);
  lines.push(`**Exported:** ${new Date().toLocaleString()}`);
  lines.push(`**Turns:** ${groups.length}`);
  lines.push("");

  // Track stats for the debug footer
  let turnsNoResponse = [];
  let toolErrors = 0;
  let missingSummaries = 0;

  groups.forEach((g, i) => {
    const turnNum = i + 1;
    const time = g.voice?.time || g.result?.time || "";
    lines.push(`---`);
    lines.push("");
    lines.push(`## Turn ${turnNum}${time ? ` (${time})` : ""}`);
    lines.push("");

    // Voice input
    if (g.voice) {
      lines.push(`### Voice Input`);
      lines.push(`> ${g.voice.text}`);
      lines.push("");
    }

    // Tool use steps
    const errorSteps = g.steps.filter((s) => s._error);
    const normalSteps = g.steps.filter((s) => !s._error);
    toolErrors += errorSteps.length;

    if (normalSteps.length > 0) {
      lines.push(`### Tool Use (${normalSteps.length} step${normalSteps.length > 1 ? "s" : ""})`);
      normalSteps.forEach((s, si) => {
        lines.push(`${si + 1}. ${formatToolStep(s.text)}`);
      });
      lines.push("");
    }

    if (errorSteps.length > 0) {
      lines.push(`### Errors`);
      errorSteps.forEach((s) => {
        lines.push(`- **Error:** ${s.text}`);
        if (s._errorDetail) {
          lines.push("  ```");
          lines.push(`  ${s._errorDetail}`);
          lines.push("  ```");
        }
      });
      lines.push("");
    }

    // Approval
    if (g.approval) {
      lines.push(`### Approval Required`);
      lines.push(`> ${g.approval.text}`);
      lines.push("");
    }

    // Claude response
    if (g.result) {
      lines.push(`### Claude Response`);
      lines.push(g.result.text || "*Empty response*");
      lines.push("");
    } else if (g.steps.length > 0) {
      lines.push(`### Claude Response`);
      lines.push(`**No response generated**`);
      lines.push("");
      turnsNoResponse.push(turnNum);
    }

    // Gemini spoken summary
    if (g.summary) {
      lines.push(`### Spoken Summary`);
      lines.push(`_${g.summary.text}_`);
      lines.push("");
    } else if (g.result) {
      missingSummaries++;
    }
  });

  // Debug summary footer
  lines.push(`---`);
  lines.push("");
  lines.push(`## Debug Summary`);
  if (turnsNoResponse.length > 0) {
    lines.push(`- Turns with no Claude response: ${turnsNoResponse.join(", ")}`);
  } else {
    lines.push(`- All turns produced a Claude response`);
  }
  lines.push(`- Tool errors: ${toolErrors}`);
  lines.push(`- Missing Gemini summaries: ${missingSummaries} / ${groups.length} turns`);
  lines.push("");

  return lines.join("\n");
}

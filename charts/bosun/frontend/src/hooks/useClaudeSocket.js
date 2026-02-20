import { useState, useEffect, useRef, useCallback } from "react";

// ── Helpers ────────────────────────────────────────────────────────────────
function now() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function buildArtifactLabel(name, input) {
  if (!name) return "Output";
  const lower = name.toLowerCase();
  if (lower.includes("screenshot")) return "Screenshot";
  if (lower.includes("snapshot")) return "Page snapshot";

  if (input) {
    switch (name) {
      case "Read":
      case "Write":
      case "Edit":
        return (input.file_path || "").split("/").pop() || name;
      case "Bash": {
        const cmd = (input.command || "").split(/[|;&\n]/).shift().trim();
        return cmd.length > 40 ? cmd.slice(0, 37) + "..." : cmd || "Terminal";
      }
      case "Grep":
        return `grep ${(input.pattern || "").slice(0, 30)}`;
      case "Glob":
        return input.pattern || "File search";
      case "WebFetch": {
        try { return new URL(input.url).hostname; } catch { return "Web"; }
      }
    }
  }

  // Fallback when input is unavailable (streaming path)
  const fallback = {
    Read: "File contents", Bash: "Terminal", Write: "Write result",
    Edit: "Edit result", Glob: "File search", Grep: "Code search",
    WebFetch: "Web content",
  };
  return fallback[name] || name;
}

function looksLikeError(output, isError) {
  if (isError) return true;
  if (!output || output.length < 40) return false;
  const s = output.slice(0, 500);
  // HTML error pages (5xx, 4xx from proxies/servers)
  if (/<!DOCTYPE|<html/i.test(s) && /\b[45]\d{2}\b/.test(s)) return true;
  // Common error patterns that shouldn't become artifacts
  if (/^(Error|Traceback|FATAL|panic:)/m.test(s)) return true;
  return false;
}

function parseDiff(text) {
  if (!text) return [];
  return text.split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
      return { t: "h", x: line };
    }
    if (line.startsWith("+")) return { t: "+", x: line };
    if (line.startsWith("-")) return { t: "-", x: line };
    return { t: "c", x: line };
  });
}

// ── WebSocket hook ─────────────────────────────────────────────────────────
export function useClaudeSocket({ onResult: onResultCb } = {}) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("vc-session-id"));
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(null);
  const [prs, setPrs] = useState([]);
  const [todos, setTodos] = useState([]);
  const [subagents, setSubagents] = useState({}); // tool_use_id → {name, desc, type, toolCount, steps[]}
  const [turnStart, setTurnStart] = useState(null);
  const [usage, setUsage] = useState(null);
  const streamBufRef = useRef("");
  const msgIdRef = useRef(0);
  const onResultRef = useRef(onResultCb);
  onResultRef.current = onResultCb;
  const toolInfoRef = useRef(new Map()); // tool_use_id → { name, input }

  const nextId = () => ++msgIdRef.current;

  const disposedRef = useRef(false);

  const connect = useCallback(() => {
    if (disposedRef.current) return;
    // Close any existing connection first
    if (wsRef.current) {
      const old = wsRef.current;
      wsRef.current = null;
      old.onclose = null; // prevent reconnect loop
      old.close();
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // URL params take priority over localStorage for session resume
      const urlSid = new URLSearchParams(window.location.search).get("session");
      const saved = urlSid || localStorage.getItem("vc-session-id");
      if (saved) {
        ws.send(JSON.stringify({ type: "resume", session_id: saved }));
        if (urlSid) localStorage.setItem("vc-session-id", urlSid);
      }
    };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      switch (msg.type) {
        case "session_init":
          setSessionId(msg.session_id);
          localStorage.setItem("vc-session-id", msg.session_id);
          break;

        case "assistant_text":
          streamBufRef.current += msg.content;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), { ...last, text: streamBufRef.current }];
            }
            return prev;
          });
          break;

        case "assistant_start":
          streamBufRef.current = "";
          setStreaming(true);
          setTurnStart((prev) => prev || Date.now()); // Only set on first start, not sub-turns
          setUsage(null);
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "thinking", text: "Working...", _streaming: true },
          ]);
          break;

        case "assistant_done":
          // Don't setStreaming(false) here — with subagents, assistant_done fires
          // per sub-turn. Only the final "result" event should end streaming.
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), { ...last, status: "done", _streaming: false }];
            }
            return prev;
          });
          break;

        case "tool_use":
          if (msg.tool_use_id) {
            toolInfoRef.current.set(msg.tool_use_id, { name: msg.name, input: msg.input });
          }
          // Track tool calls within subagents
          if (msg.parent_tool_use_id) {
            setSubagents((prev) => {
              const agent = prev[msg.parent_tool_use_id];
              if (agent) {
                const steps = [...agent.steps, `${msg.name}: ${msg.summary || ""}`].slice(-3);
                return { ...prev, [msg.parent_tool_use_id]: { ...agent, toolCount: agent.toolCount + 1, steps } };
              }
              return prev;
            });
          }
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "tool", text: `${msg.name}: ${msg.summary || ""}` },
          ]);
          break;

        case "tool_approval":
          setPendingApproval(msg);
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(), role: "claude", time: now(), status: "approval",
              text: msg.description || `${msg.name}: ${JSON.stringify(msg.input).slice(0, 120)}`,
              _approvalId: msg.tool_use_id,
            },
          ]);
          break;

        case "tool_result": {
          // Look up the tool_use info we tracked earlier for better labels
          const info = toolInfoRef.current.get(msg.tool_use_id) || {};
          const toolName = msg.name || info.name || "";
          const toolInput = info.input;
          const toolLabel = buildArtifactLabel(toolName, toolInput);
          const isErr = looksLikeError(msg.output, msg.is_error);
          // Clean up the tracking map
          if (msg.tool_use_id) toolInfoRef.current.delete(msg.tool_use_id);
          let toolArtifact = null;
          if (isErr) {
            // Error results: no artifact, store error detail for inline display
            setMessages((prev) => [
              ...prev,
              {
                id: nextId(), role: "claude", time: now(), status: "tool",
                text: `${toolLabel}: error`,
                _error: true,
                _errorDetail: msg.output,
              },
            ]);
          } else {
            if (msg.image) {
              toolArtifact = { type: "image", label: toolLabel, data: msg.image.data, mimeType: msg.image.mimeType, toolName };
            } else if (msg.output && msg.output.length > 80) {
              toolArtifact = { type: "output", label: toolLabel, data: msg.output, toolName };
            }
            setMessages((prev) => [
              ...prev,
              {
                id: nextId(), role: "claude", time: now(), status: "tool",
                text: msg.image ? `Image: ${toolLabel}` : `Result: ${(msg.output || "").slice(0, 200)}`,
                artifact: toolArtifact,
              },
            ]);
          }
          break;
        }

        case "mermaid_artifact":
          setMessages((prev) => {
            // Attach mermaid artifact to the most recent claude message
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === "claude") {
                const updated = [...prev];
                updated[i] = {
                  ...updated[i],
                  artifact: { type: "mermaid", label: msg.label || "diagram", data: msg.code },
                };
                return updated;
              }
            }
            return prev;
          });
          break;

        case "diff":
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last) {
              const diffLines = parseDiff(msg.content);
              const adds = diffLines.filter((l) => l.t === "+").length;
              const dels = diffLines.filter((l) => l.t === "-").length;
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  artifact: { type: "diff", label: msg.file || "changes", data: diffLines, additions: adds, deletions: dels },
                },
              ];
            }
            return prev;
          });
          break;

        case "result": {
          setStreaming(false);
          setTurnStart(null);
          setSubagents({});
          // Don't clear todos — they persist for TTS context
          // The agent turn is complete — ensure the messages array has a "done"
          // message with the full result text so exports/grouping work correctly.
          const fullText = (msg.full_text || "").trim();
          console.log("[bosun] result received:", { hasText: !!fullText, len: fullText.length, tools: msg.tool_summaries?.length || 0, turns: msg.num_turns, isError: msg.is_error, speculative: !!msg.speculative_summary, hasCallback: !!onResultRef.current });
          if (!fullText && msg.tool_summaries?.length) {
            console.warn("[bosun] tools ran but no text response — Claude may have terminated early (turns:", msg.num_turns, "is_error:", msg.is_error, ")");
          }

          if (fullText || msg.tool_summaries?.length) {
            setMessages((prev) => {
              // Find the last voice message to scope our search to the current turn
              const lastVoiceIdx = prev.findLastIndex((m) => m.role === "voice");
              // Look for an existing "done" message from assistant_done in this turn
              const existingIdx = prev.findLastIndex(
                (m, i) => i > lastVoiceIdx && m.role === "claude" && m.status === "done",
              );
              if (existingIdx >= 0) {
                // Update the existing done message with the authoritative full text
                const updated = [...prev];
                updated[existingIdx] = { ...updated[existingIdx], text: fullText };
                return updated;
              }
              // No done message yet (e.g. tool-only turn with no text) — create one
              return [
                ...prev,
                { id: nextId(), role: "claude", time: now(), status: "done", text: fullText },
              ];
            });
          }

          // Fire the onResult callback for TTS/summary generation
          if (onResultRef.current && (fullText || msg.tool_summaries?.length)) {
            onResultRef.current(fullText, msg.tool_summaries, msg.speculative_summary || null);
          } else if (!fullText && !msg.tool_summaries?.length) {
            console.warn("[bosun] result message had no content:", msg);
          }
          break;
        }

        case "queued":
          // Message was queued because agent is busy — mark the existing voice message
          setMessages((prev) => {
            // Find the most recent voice message matching this text and mark it queued
            const idx = prev.findLastIndex((m) => m.role === "voice" && m.text === msg.text);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], _queued: true, _queuePos: msg.position };
              return updated;
            }
            return prev;
          });
          break;

        case "queue_drain":
          // A queued message is now being sent to the agent — unmark it
          setMessages((prev) =>
            prev.map((m) => (m._queued && m.text === msg.text ? { ...m, _queued: false } : m)),
          );
          setStreaming(true);
          break;

        case "cancelled":
          setStreaming(false);
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "done", text: "Cancelled." },
          ]);
          break;

        case "compacted":
          setStreaming(false);
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "done", text: "Session compacted. Context carried forward." },
          ]);
          break;

        case "status":
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "done", text: msg.message },
          ]);
          break;

        case "error":
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "done", text: `Error: ${msg.message}` },
          ]);
          setStreaming(false);
          break;

        case "pr_detected":
          setPrs((prev) => {
            const exists = prev.some((p) => p.pr_number === msg.pr.pr_number && p.repo === msg.pr.repo);
            return exists ? prev : [...prev, msg.pr];
          });
          // Attach PR ref to most recent claude message for inline rendering
          setMessages((prev) => {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === "claude") {
                const updated = [...prev];
                const existing = updated[i]._prs || [];
                updated[i] = { ...updated[i], _prs: [...existing, msg.pr] };
                return updated;
              }
            }
            return prev;
          });
          break;

        case "todo_update":
          setTodos(msg.todos || []);
          break;

        case "subagent_start":
          setSubagents((prev) => ({
            ...prev,
            [msg.tool_use_id]: {
              name: msg.name || "",
              desc: msg.description || "",
              type: msg.subagent_type || "",
              toolCount: prev[msg.tool_use_id]?.toolCount || 0,
              steps: prev[msg.tool_use_id]?.steps || [],
            },
          }));
          break;

        case "usage_update":
          setUsage({ input_tokens: msg.input_tokens, output_tokens: msg.output_tokens });
          break;

        case "heartbeat":
          break;

        case "prs_update":
          setPrs(msg.prs);
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Only reconnect if not disposed (component still mounted)
      if (!disposedRef.current) {
        setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    disposedRef.current = false;
    connect();
    return () => {
      disposedRef.current = true;
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null;
        ws.onclose = null; // prevent reconnect on unmount
        ws.close();
      }
    };
  }, [connect]);

  const lastSummaryRef = useRef("");

  const send = useCallback((text) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "voice", time: now(), text },
    ]);
    const msg = { type: "message", text };
    if (lastSummaryRef.current) {
      msg.summary_context = lastSummaryRef.current;
      lastSummaryRef.current = "";
    }
    wsRef.current.send(JSON.stringify(msg));
  }, []);

  const approve = useCallback((toolUseId) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "approve", tool_use_id: toolUseId }));
    setPendingApproval(null);
    // Update the approval message to show it was approved
    setMessages((prev) =>
      prev.map((m) => (m._approvalId === toolUseId ? { ...m, status: "tool", text: `Approved: ${m.text}` } : m)),
    );
  }, []);

  const reject = useCallback((toolUseId) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "reject", tool_use_id: toolUseId }));
    setPendingApproval(null);
    setMessages((prev) =>
      prev.map((m) => (m._approvalId === toolUseId ? { ...m, status: "done", text: `Rejected: ${m.text}` } : m)),
    );
  }, []);

  const newSession = useCallback(() => {
    localStorage.removeItem("vc-session-id");
    setSessionId(null);
    setMessages([]);
    setStreaming(false);
    setPendingApproval(null);
    setPrs([]);
    setTodos([]);
    setSubagents({});
    setTurnStart(null);
    setUsage(null);
    // Clear URL param
    const url = new URL(window.location);
    url.searchParams.delete("session");
    window.history.pushState({}, "", url);
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: "new_session" }));
    }
  }, []);

  const resumeSession = useCallback(async (sid, force = false) => {
    if (sid === sessionId && !force) return; // Already on this session

    setSessionId(sid);
    localStorage.setItem("vc-session-id", sid);
    setStreaming(false);
    setPendingApproval(null);

    // Update URL
    const url = new URL(window.location);
    url.searchParams.set("session", sid);
    window.history.pushState({}, "", url);

    // Tell backend to use this session for future messages
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "resume", session_id: sid }));
    }

    // Load conversation history, artifacts, summaries, and PRs from API
    try {
      const [msgRes, artRes, sumRes, prRes] = await Promise.all([
        fetch(`/api/sessions/${sid}/messages`),
        fetch(`/api/sessions/${sid}/artifacts`),
        fetch(`/api/sessions/${sid}/summaries`),
        fetch(`/api/sessions/${sid}/prs`),
      ]);
      const msgData = await msgRes.json();
      const artData = await artRes.json();
      const sumData = await sumRes.json();
      const prData = await prRes.json();

      // Restore PRs for this session
      if (prData.prs?.length) setPrs(prData.prs);
      else setPrs([]);

      let loaded = [];
      if (msgData.messages) {
        loaded = msgData.messages.map((m, i) => ({
          ...m,
          id: -(i + 1), // Negative IDs for historical messages
          time: "",
        }));
      }

      // Merge artifacts back into messages by msg_id
      if (artData.artifacts?.length) {
        const artsByMsg = {};
        for (const a of artData.artifacts) {
          if (!artsByMsg[a.msg_id]) artsByMsg[a.msg_id] = [];
          artsByMsg[a.msg_id].push(a);
        }
        // Attach artifacts to the closest preceding claude message
        for (const arts of Object.values(artsByMsg)) {
          for (const art of arts) {
            // Find a claude message to attach to, or append as standalone
            const artifact = {
              type: art.type,
              label: art.label,
              data: art.data,
              mimeType: art.mimeType,
            };
            // Try to attach to last claude result message without an artifact
            let attached = false;
            for (let i = loaded.length - 1; i >= 0; i--) {
              if (loaded[i].role === "claude" && loaded[i].status === "done" && !loaded[i].artifact) {
                loaded[i] = { ...loaded[i], artifact };
                attached = true;
                break;
              }
            }
            if (!attached) {
              loaded.push({
                id: nextId(),
                role: "claude",
                status: "done",
                time: "",
                text: `[${art.type}: ${art.label}]`,
                artifact,
              });
            }
          }
        }
      }

      // Inject summaries as gemini-role messages
      if (sumData.summaries?.length) {
        for (const s of sumData.summaries) {
          loaded.push({
            id: nextId(),
            role: "gemini",
            time: "",
            text: s.text,
          });
        }
      }

      setMessages(loaded);
    } catch (e) {
      console.warn("Failed to load session history:", e);
      setMessages([]);
    }
  }, [sessionId]);

  const addGeminiMessage = useCallback((text) => {
    lastSummaryRef.current = text;
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "gemini", time: now(), text },
    ]);
  }, []);

  return { connected, sessionId, messages, streaming, pendingApproval, prs, todos, subagents, turnStart, usage, send, approve, reject, newSession, resumeSession, wsRef, addGeminiMessage };
}

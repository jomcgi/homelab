import { useState, useRef, useCallback } from "react";
import { confirmTTS } from "./useTTS.js";

// ── Voice command classification hook ──────────────────────────────────────
export function useVoiceCommands({ send, newSession, wsRef, tts, streaming, pendingApproval, approve, reject }) {
  const lastAudioRef = useRef(null);      // For "repeat" command
  const [actions, setActions] = useState([]); // Suggested follow-up actions

  // Save last TTS audio blob for replay
  const saveLastAudio = useCallback((blob) => {
    lastAudioRef.current = blob;
  }, []);

  const replayLastAudio = useCallback(() => {
    if (!lastAudioRef.current) {
      confirmTTS("Nothing to repeat");
      return;
    }
    const url = URL.createObjectURL(lastAudioRef.current);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play().catch(() => URL.revokeObjectURL(url));
  }, []);

  const clearActions = useCallback(() => setActions([]), []);

  const executeCommand = useCallback(async (intent, params) => {
    switch (intent) {
      case "new_session":
        newSession();
        confirmTTS("Starting new session");
        break;
      case "cancel":
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "cancel" }));
        }
        confirmTTS("Cancelled");
        break;
      case "repeat":
        replayLastAudio();
        break;
      case "mute":
        if (tts.enabled) tts.toggle();
        confirmTTS("Muted");
        break;
      case "unmute":
        if (!tts.enabled) tts.toggle();
        confirmTTS("Unmuted");
        break;
      case "approve":
        if (pendingApproval) {
          approve(pendingApproval.tool_use_id);
          confirmTTS("Approved");
        } else {
          confirmTTS("Nothing to approve");
        }
        break;
      case "reject":
        if (pendingApproval) {
          reject(pendingApproval.tool_use_id);
          confirmTTS("Rejected");
        } else {
          confirmTTS("Nothing to reject");
        }
        break;
      case "status": {
        const statusText = streaming ? "Claude is currently working" : "Claude is idle";
        confirmTTS(statusText);
        break;
      }
      case "list_sessions":
        try {
          const res = await fetch("/api/sessions?limit=3");
          const data = await res.json();
          const sessions = data.sessions || [];
          if (sessions.length === 0) {
            confirmTTS("No recent sessions");
          } else {
            const names = sessions.map((s, i) => `${i + 1}: ${s.preview.slice(0, 40)}`).join(". ");
            confirmTTS(`Recent sessions: ${names}`);
          }
        } catch {
          confirmTTS("Could not load sessions");
        }
        break;
      case "switch_session":
        try {
          const res = await fetch("/api/sessions/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: params?.query || "" }),
          });
          const data = await res.json();
          if (data.matches?.length > 0) {
            confirmTTS(`Switching to: ${data.matches[0].preview.slice(0, 40)}`);
            // The actual switch is handled by the caller (App)
            return { switchTo: data.matches[0].id };
          } else {
            confirmTTS("No matching session found");
          }
        } catch {
          confirmTTS("Could not search sessions");
        }
        break;
      case "compact": {
        const directive = params?.query || "";
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "compact", message: directive }));
        }
        confirmTTS("Compacting session context");
        break;
      }
      default:
        send(params?.query || intent);
    }
  }, [send, newSession, wsRef, tts, streaming, pendingApproval, approve, reject, replayLastAudio]);

  // Client-side fast command patterns
  const FAST_COMMANDS = useRef([
    { pattern: /^(new session|start over|fresh start)$/i, intent: "new_session" },
    { pattern: /^(cancel|stop|nevermind)$/i, intent: "cancel" },
    { pattern: /^(say that again|repeat|read that again)$/i, intent: "repeat" },
    { pattern: /^(mute|be quiet|shut up)$/i, intent: "mute" },
    { pattern: /^(unmute|speak|talk to me)$/i, intent: "unmute" },
    { pattern: /^(approve|yes|do it|go ahead)$/i, intent: "approve" },
    { pattern: /^(reject|no|don't|nope)$/i, intent: "reject" },
    { pattern: /^(what's happening|are you busy|are you working)$/i, intent: "status" },
  ]);

  const classify = useCallback(async (text) => {
    const trimmed = text.trim();

    // 1. Fast path — client regex
    for (const { pattern, intent } of FAST_COMMANDS.current) {
      if (pattern.test(trimmed)) {
        const result = await executeCommand(intent);
        return result;
      }
    }

    // 2. Skip classification for long messages (>20 words = definitely for Claude)
    if (trimmed.split(/\s+/).length > 20) {
      send(trimmed);
      return;
    }

    // 3. Gemini intent classification for short ambiguous input
    try {
      const res = await fetch("/api/intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: trimmed,
          context: { streaming, has_pending_approval: !!pendingApproval },
        }),
      });
      const data = await res.json();

      if (data.intent === "message" || !data.intent) {
        send(trimmed);  // Forward to Claude
      } else {
        const result = await executeCommand(data.intent, data.params);
        return result;
      }
    } catch {
      send(trimmed);  // On error, just send to Claude
    }
  }, [send, streaming, pendingApproval, executeCommand]);

  return { classify, actions, setActions, clearActions, saveLastAudio, replayLastAudio };
}

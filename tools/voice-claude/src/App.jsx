import { useState, useEffect, useRef, useCallback } from "react";
import {
  Mic, MicOff, ChevronDown, ChevronUp, ChevronRight, Check, AlertTriangle,
  Volume2, VolumeX, Terminal, Plus, X, PanelRightOpen, PanelRightClose, GitBranch,
  FileCode, MoreHorizontal, Loader2, WifiOff, Wifi,
} from "lucide-react";

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg: "#FFFFFF",
  bgSub: "#FAFAFA",
  surface: "#F4F4F5",
  surfaceHover: "#EBEBED",
  border: "#E4E4E7",
  borderLight: "#F0F0F2",
  text: "#18181B",
  textSec: "#52525B",
  textTer: "#A1A1AA",
  textFaint: "#D4D4D8",
  you: "#047857",
  youBg: "#ECFDF5",
  youBorder: "#A7F3D0",
  voice: "#7C3AED",
  voiceBg: "#F5F3FF",
  voiceBorder: "#DDD6FE",
  approval: "#B45309",
  approvalBg: "#FFFBEB",
  approvalBorder: "#FDE68A",
  success: "#059669",
  danger: "#DC2626",
  micOn: "#DC2626",
  addGreen: "#16A34A",
  addBg: "#F0FDF4",
  delRed: "#DC2626",
  delBg: "#FEF2F2",
  accentBlue: "#2563EB",
};

const sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const mono = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace";

// ── Responsive hook ────────────────────────────────────────────────────────
function useBreakpoint() {
  const [bp, setBp] = useState(() =>
    typeof window === "undefined" ? "desktop" : window.innerWidth < 768 ? "mobile" : "desktop",
  );
  useEffect(() => {
    const check = () => setBp(window.innerWidth < 768 ? "mobile" : "desktop");
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return bp;
}

// ── WebSocket hook ─────────────────────────────────────────────────────────
function useClaudeSocket({ onResult: onResultCb } = {}) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("vc-session-id"));
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(null);
  const streamBufRef = useRef("");
  const msgIdRef = useRef(0);
  const onResultRef = useRef(onResultCb);
  onResultRef.current = onResultCb;

  const nextId = () => ++msgIdRef.current;

  const connect = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Resume session if we have one
      const saved = localStorage.getItem("vc-session-id");
      if (saved) {
        ws.send(JSON.stringify({ type: "resume", session_id: saved }));
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
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "thinking", text: "Working...", _streaming: true },
          ]);
          break;

        case "assistant_done":
          setStreaming(false);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), { ...last, status: "done", _streaming: false }];
            }
            return prev;
          });
          break;

        case "tool_use":
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

        case "tool_result":
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(), role: "claude", time: now(), status: "tool",
              text: `Result: ${(msg.output || "").slice(0, 200)}`,
              artifact: msg.output && msg.output.length > 80
                ? { type: "output", label: msg.name || "output", data: msg.output }
                : null,
            },
          ]);
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

        case "result":
          // The agent is done — fire the onResult callback with full turn text
          if (msg.full_text && onResultRef.current) {
            onResultRef.current(msg.full_text);
          }
          break;

        case "error":
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "claude", time: now(), status: "done", text: `Error: ${msg.message}` },
          ]);
          setStreaming(false);
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Reconnect after delay
      setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const send = useCallback((text) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "voice", time: now(), text },
    ]);
    wsRef.current.send(JSON.stringify({ type: "message", text }));
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
    // Clear URL param
    const url = new URL(window.location);
    url.searchParams.delete("session");
    window.history.pushState({}, "", url);
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: "new_session" }));
    }
  }, []);

  const resumeSession = useCallback(async (sid) => {
    if (sid === sessionId) return; // Already on this session

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

    // Load conversation history from API
    try {
      const res = await fetch(`/api/sessions/${sid}/messages`);
      const data = await res.json();
      if (data.messages) {
        const loaded = data.messages.map((m, i) => ({
          ...m,
          id: -(i + 1), // Negative IDs for historical messages
          time: "",
        }));
        setMessages(loaded);
      }
    } catch (e) {
      console.warn("Failed to load session history:", e);
      setMessages([]);
    }
  }, [sessionId]);

  return { connected, sessionId, messages, streaming, pendingApproval, send, approve, reject, newSession, resumeSession };
}

// ── Web Speech API hook ────────────────────────────────────────────────────
function useVoiceInput() {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef(null);

  const supported = typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  const start = useCallback((onResult) => {
    if (!supported) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (e) => {
      let finalText = "";
      let interimText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          finalText += transcript;
        } else {
          interimText += transcript;
        }
      }
      setInterim(interimText);
      if (finalText.trim()) {
        onResult(finalText.trim());
        setInterim("");
      }
    };

    recognition.onerror = (e) => {
      if (e.error !== "no-speech" && e.error !== "aborted") {
        console.warn("Speech recognition error:", e.error);
      }
    };

    recognition.onend = () => {
      // Restart if still supposed to be listening
      if (recognitionRef.current === recognition) {
        try { recognition.start(); } catch { /* ignore */ }
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [supported]);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      const r = recognitionRef.current;
      recognitionRef.current = null;
      r.stop();
    }
    setListening(false);
    setInterim("");
  }, []);

  return { listening, interim, supported, start, stop };
}

// ── TTS hook (Gemini-powered with browser fallback) ────────────────────────
function useTTS() {
  const [enabled, setEnabled] = useState(() => localStorage.getItem("vc-tts") !== "off");
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef(null);
  const abortRef = useRef(null);

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("vc-tts", next ? "on" : "off");
      if (!next) {
        if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
        if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
        setSpeaking(false);
      }
      return next;
    });
  }, []);

  const speak = useCallback(async (text) => {
    if (!enabled || !text) return;

    // Abort any in-flight request
    if (abortRef.current) abortRef.current.abort();
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }

    const controller = new AbortController();
    abortRef.current = controller;
    setSpeaking(true);

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, summarize: true }),
        signal: controller.signal,
      });
      const data = await res.json();

      if (data.audio) {
        // Gemini returned audio — play it
        const audioData = atob(data.audio);
        const bytes = new Uint8Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) bytes[i] = audioData.charCodeAt(i);
        const blob = new Blob([bytes], { type: data.mime_type || "audio/wav" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); };
        audio.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url); };
        await audio.play();
      } else {
        // Fallback to browser TTS if Gemini unavailable
        if (window.speechSynthesis) {
          let toSpeak = text;
          if (text.length > 300) {
            const cut = text.slice(0, 300);
            const lp = cut.lastIndexOf(".");
            toSpeak = lp > 100 ? cut.slice(0, lp + 1) : cut + "...";
          }
          const utterance = new SpeechSynthesisUtterance(toSpeak);
          utterance.rate = 1.1;
          utterance.onend = () => setSpeaking(false);
          utterance.onerror = () => setSpeaking(false);
          window.speechSynthesis.speak(utterance);
        } else {
          setSpeaking(false);
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") console.warn("TTS error:", e);
      setSpeaking(false);
    }
  }, [enabled]);

  const stop = useCallback(() => {
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  return { enabled, toggle, speak, stop, speaking };
}

// ── Helpers ────────────────────────────────────────────────────────────────
function now() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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

// ── Shared Components ──────────────────────────────────────────────────────

function VoiceDot({ state, size }) {
  const sz = size || 8;
  const color = state === "speaking" ? C.voice : state === "listening" ? C.success : C.textFaint;
  return (
    <div style={{ position: "relative", width: sz, height: sz, flexShrink: 0 }}>
      <div style={{ width: sz, height: sz, borderRadius: "50%", backgroundColor: color, transition: "background-color 200ms" }} />
      {state !== "off" && (
        <div style={{
          position: "absolute", inset: -3, borderRadius: "50%",
          border: `1.5px solid ${color}`, opacity: 0.35,
          animation: "vcc-ring 2s ease-out infinite",
        }} />
      )}
    </div>
  );
}

function ArtifactCard({ artifact, onClick, selected }) {
  if (!artifact) return null;
  const icons = { diff: <FileCode size={13} />, output: <Terminal size={13} />, mermaid: <GitBranch size={13} /> };
  return (
    <button onClick={onClick} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "5px 10px", borderRadius: 6, cursor: "pointer",
      border: selected ? `1.5px solid ${C.accentBlue}` : `1px solid ${C.border}`,
      backgroundColor: selected ? "#EFF6FF" : C.surface,
      fontFamily: mono, fontSize: 12, color: selected ? C.accentBlue : C.textSec,
      marginTop: 6, marginRight: 6, transition: "all 150ms",
    }}>
      {icons[artifact.type]}
      <span>{artifact.label}</span>
      {artifact.additions > 0 && <span style={{ color: C.addGreen }}>+{artifact.additions}</span>}
      {artifact.deletions > 0 && <span style={{ color: C.delRed }}>{"-"}{artifact.deletions}</span>}
    </button>
  );
}

function InlineArtifact({ artifact }) {
  const [open, setOpen] = useState(false);
  if (!artifact) return null;

  if (artifact.type === "diff") {
    const lines = artifact.data;
    const show = open ? lines : lines.slice(0, 8);
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <button onClick={() => setOpen(!open)} style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px 12px", backgroundColor: C.surface, border: "none",
          borderBottom: `1px solid ${C.border}`, cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <FileCode size={13} />
            <span style={{ fontFamily: mono }}>{artifact.label}</span>
            {artifact.additions > 0 && <span style={{ color: C.addGreen, fontFamily: mono, fontSize: 11 }}>+{artifact.additions}</span>}
            {artifact.deletions > 0 && <span style={{ color: C.delRed, fontFamily: mono, fontSize: 11 }}>{"-"}{artifact.deletions}</span>}
          </span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <div style={{ padding: "6px 0", overflowX: "auto", fontFamily: mono, fontSize: 12, lineHeight: 1.7 }}>
          {show.map((l, i) => (
            <div key={i} style={{
              padding: "0 12px", whiteSpace: "pre",
              color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
              backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
            }}>{l.x}</div>
          ))}
          {!open && lines.length > 8 && (
            <div style={{ padding: "4px 12px", fontSize: 11, color: C.textTer }}>+{lines.length - 8} more lines</div>
          )}
        </div>
      </div>
    );
  }
  if (artifact.type === "output") {
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "7px 12px", backgroundColor: C.surface, borderBottom: `1px solid ${C.border}`, fontSize: 12, color: C.textSec, display: "flex", alignItems: "center", gap: 6 }}>
          <Terminal size={13} /> {artifact.label}
        </div>
        <pre style={{ padding: "8px 12px", margin: 0, overflowX: "auto", fontFamily: mono, fontSize: 12, lineHeight: 1.6, color: C.text }}>{artifact.data}</pre>
      </div>
    );
  }
  if (artifact.type === "mermaid") {
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <button onClick={() => setOpen(!open)} style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px 12px", backgroundColor: C.surface, border: "none",
          borderBottom: open ? `1px solid ${C.border}` : "none", cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><GitBranch size={13} /> {artifact.label}</span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {open && <pre style={{ padding: "8px 12px", margin: 0, overflowX: "auto", fontFamily: mono, fontSize: 11, lineHeight: 1.5, color: C.you }}>{artifact.data}</pre>}
      </div>
    );
  }
  return null;
}

// ── Detail Panel ───────────────────────────────────────────────────────────
function DetailPanel({ artifact, onClose }) {
  if (!artifact) return (
    <div style={{
      height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
      color: C.textFaint, fontFamily: sans, fontSize: 13,
      flexDirection: "column", gap: 8, padding: 32, textAlign: "center",
    }}>
      <FileCode size={32} color={C.textFaint} strokeWidth={1.2} />
      <span>Select a diff, output, or diagram to inspect it here</span>
    </div>
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {artifact.type === "diff" && <FileCode size={14} color={C.textSec} />}
          {artifact.type === "output" && <Terminal size={14} color={C.textSec} />}
          {artifact.type === "mermaid" && <GitBranch size={14} color={C.textSec} />}
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: sans }}>{artifact.label}</span>
          {artifact.additions > 0 && <span style={{ fontSize: 12, color: C.addGreen, fontFamily: mono }}>+{artifact.additions}</span>}
          {artifact.deletions > 0 && <span style={{ fontSize: 12, color: C.delRed, fontFamily: mono }}>{"-"}{artifact.deletions}</span>}
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.textTer, padding: 4, display: "flex" }}>
          <X size={16} />
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
        {artifact.type === "diff" && (
          <div style={{ fontFamily: mono, fontSize: 13, lineHeight: 1.8, minWidth: "fit-content" }}>
            {artifact.data.map((l, i) => (
              <div key={i} style={{
                padding: "0 16px", whiteSpace: "pre",
                color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
                backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
              }}>{l.x}</div>
            ))}
          </div>
        )}
        {artifact.type === "output" && (
          <pre style={{ padding: "12px 16px", margin: 0, fontFamily: mono, fontSize: 13, lineHeight: 1.7, color: C.text, whiteSpace: "pre-wrap" }}>{artifact.data}</pre>
        )}
        {artifact.type === "mermaid" && (
          <pre style={{ padding: "12px 16px", margin: 0, fontFamily: mono, fontSize: 12, lineHeight: 1.6, color: C.you }}>{artifact.data}</pre>
        )}
      </div>
    </div>
  );
}

// ── Message grouping ───────────────────────────────────────────────────────
function useGroups(messages) {
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

function TranscriptView({ messages, onSelectArtifact, selectedArtifactId, isMobile, onApprove, onReject }) {
  const groups = useGroups(messages);
  const [expandedSteps, setExpandedSteps] = useState({});

  return (
    <div>
      {groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 28 }}>
          {/* Voice input */}
          {g.voice && (
            <div style={{
              padding: "12px 16px", marginBottom: 10,
              backgroundColor: C.youBg, borderRadius: 12,
              borderLeft: `3px solid ${C.you}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                <Mic size={13} color={C.you} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.you }}>You</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.voice.time}</span>
              </div>
              <div style={{ fontSize: 15, color: C.text, lineHeight: 1.55 }}>{g.voice.text}</div>
            </div>
          )}

          {/* Collapsed intermediate steps */}
          {g.steps.length > 0 && (
            <button
              onClick={() => setExpandedSteps((p) => ({ ...p, [gi]: !p[gi] }))}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "3px 0", margin: "2px 0 6px",
                background: "none", border: "none", cursor: "pointer",
                fontFamily: sans, fontSize: 12, color: C.textTer,
              }}
            >
              {expandedSteps[gi] ? <ChevronUp size={12} /> : <ChevronRight size={12} />}
              <MoreHorizontal size={12} />
              <span>{g.steps.length} step{g.steps.length > 1 ? "s" : ""}</span>
              {expandedSteps[gi] && (
                <span style={{ marginLeft: 4, color: C.textTer }}>
                  {g.steps.map((s) => s.text).join(" \u2192 ")}
                </span>
              )}
            </button>
          )}

          {/* Approval */}
          {g.approval && (
            <div style={{
              margin: "8px 0", padding: "12px 16px",
              backgroundColor: C.approvalBg, border: `1px solid ${C.approvalBorder}`,
              borderRadius: 10, display: "flex", alignItems: "center", gap: 12,
              flexWrap: "wrap",
            }}>
              <AlertTriangle size={16} color={C.approval} style={{ flexShrink: 0 }} />
              <span style={{ fontFamily: mono, fontSize: 13, color: C.text, flex: 1, minWidth: 160 }}>{g.approval.text}</span>
              {g.approval._approvalId && (
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => onApprove(g.approval._approvalId)} style={{
                    padding: "7px 20px", borderRadius: 7, border: "none", cursor: "pointer",
                    backgroundColor: C.text, color: C.bg, fontFamily: sans, fontSize: 13, fontWeight: 500,
                  }}>Approve</button>
                  <button onClick={() => onReject(g.approval._approvalId)} style={{
                    padding: "7px 20px", borderRadius: 7, cursor: "pointer",
                    backgroundColor: "transparent", color: C.textSec,
                    border: `1px solid ${C.border}`, fontFamily: sans, fontSize: 13,
                  }}>Reject</button>
                </div>
              )}
            </div>
          )}

          {/* Claude Code result */}
          {g.result && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <Check size={13} color={C.success} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.textSec }}>Claude Code</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.result.time}</span>
              </div>
              <div style={{ fontSize: 14, color: C.textSec, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{g.result.text}</div>

              {isMobile ? (
                <>
                  {g.result.artifact && <InlineArtifact artifact={g.result.artifact} />}
                  {g.result.artifact2 && <InlineArtifact artifact={g.result.artifact2} />}
                </>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 0 }}>
                  {g.result.artifact && (
                    <ArtifactCard
                      artifact={g.result.artifact}
                      selected={selectedArtifactId === g.result.id + "-1"}
                      onClick={() => onSelectArtifact(g.result.artifact, g.result.id + "-1")}
                    />
                  )}
                  {g.result.artifact2 && (
                    <ArtifactCard
                      artifact={g.result.artifact2}
                      selected={selectedArtifactId === g.result.id + "-2"}
                      onClick={() => onSelectArtifact(g.result.artifact2, g.result.id + "-2")}
                    />
                  )}
                </div>
              )}
            </div>
          )}

          {/* Voice summary */}
          {g.summary && (
            <div style={{
              padding: "12px 16px",
              backgroundColor: C.voiceBg, borderRadius: 12,
              borderLeft: `3px solid ${C.voice}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                <Volume2 size={13} color={C.voice} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.voice }}>Spoken</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.summary.time}</span>
              </div>
              <div style={{ fontSize: 14, color: C.text, lineHeight: 1.55, fontStyle: "italic" }}>{g.summary.text}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────
// ── Session history hook ──────────────────────────────────────────────────
function useSessionHistory() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/sessions?limit=30");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (e) {
      console.warn("Failed to load sessions:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on mount
  useEffect(() => { refresh(); }, [refresh]);

  return { sessions, loading, refresh };
}

export default function App() {
  const bp = useBreakpoint();
  const tts = useTTS();
  const { connected, sessionId, messages, streaming, send, approve, reject, newSession, resumeSession } = useClaudeSocket({
    onResult: (text) => tts.speak(text),
  });
  const voice = useVoiceInput();
  const history = useSessionHistory();
  const [inp, setInp] = useState("");
  const [detailArtifact, setDetailArtifact] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [showDetail, setShowDetail] = useState(true);
  const [showRail, setShowRail] = useState(true);
  const scrollRef = useRef(null);
  const scrollAnchorRef = useRef(null);

  // Load session from URL param on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlSession = params.get("session");
    if (urlSession && urlSession !== sessionId) {
      resumeSession(urlSession);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollAnchorRef.current) {
      scrollAnchorRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, streaming]);

  const voiceState = !voice.listening ? "off" : "listening";

  const handleSubmit = () => {
    const text = inp.trim();
    if (!text) return;
    send(text);
    setInp("");
  };

  const toggleVoice = () => {
    if (voice.listening) {
      voice.stop();
    } else {
      tts.stop(); // Stop any TTS when user starts talking
      voice.start((text) => send(text));
    }
  };

  const handleSelectArtifact = useCallback((artifact, id) => {
    if (detailId === id) { setDetailArtifact(null); setDetailId(null); }
    else { setDetailArtifact(artifact); setDetailId(id); setShowDetail(true); }
  }, [detailId]);

  // ── Mobile layout ──────────────────────────────────────────────
  if (bp === "mobile") {
    return (
      <div style={{ width: "100vw", height: "100vh", backgroundColor: C.bg, fontFamily: sans, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "0 12px", height: 52, borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Voice::CC</span>
            {connected ? <Wifi size={12} color={C.success} /> : <WifiOff size={12} color={C.danger} />}
          </div>
          <VoiceDot state={voiceState} size={8} />
          {voice.listening && <span style={{ fontSize: 12, color: C.textSec }}>Listening</span>}
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "16px 12px 120px" }}>
          <TranscriptView messages={messages} onSelectArtifact={() => {}} selectedArtifactId={null} isMobile onApprove={approve} onReject={reject} />
          {streaming && (
            <div style={{ padding: "12px 0", display: "flex", alignItems: "center", gap: 8 }}>
              <Loader2 size={14} color={C.textSec} style={{ animation: "spin 1s linear infinite" }} />
              <span style={{ fontSize: 13, color: C.textSec }}>Working...</span>
            </div>
          )}
          {voice.interim && (
            <div style={{ padding: "8px 12px", color: C.textTer, fontStyle: "italic", fontSize: 14 }}>{voice.interim}</div>
          )}
        </div>

        <div style={{ borderTop: `1px solid ${C.border}`, padding: "8px 12px", backgroundColor: C.bg, flexShrink: 0, display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", border: `1px solid ${C.border}`, borderRadius: 10, padding: "0 12px", height: 40, backgroundColor: C.surface }}>
            <input
              value={inp} onChange={(e) => setInp(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
              placeholder="Type a message..."
              style={{ flex: 1, backgroundColor: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14, fontFamily: sans }}
            />
          </div>
          <button onClick={toggleVoice} style={{
            width: 44, height: 44, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0,
            border: voice.listening ? `2px solid ${C.micOn}` : `2px solid ${C.textFaint}`,
            backgroundColor: voice.listening ? "#FEF2F2" : C.bg,
          }}>
            {voice.listening ? <Mic size={18} color={C.micOn} /> : <MicOff size={18} color={C.textTer} />}
          </button>
        </div>

        <style>{`
          @keyframes vcc-ring { 0%{transform:scale(1);opacity:.35} 100%{transform:scale(1.8);opacity:0} }
          @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
          * { box-sizing: border-box; margin: 0; padding: 0; }
          input::placeholder { color: ${C.textFaint}; }
        `}</style>
      </div>
    );
  }

  // ── Desktop layout ─────────────────────────────────────────────
  const hasDetail = showDetail && detailArtifact;

  return (
    <div style={{ width: "100vw", height: "100vh", backgroundColor: C.bg, fontFamily: sans, display: "flex", overflow: "hidden" }}>

      {/* Sessions rail */}
      {showRail && (
        <div style={{
          width: 220, flexShrink: 0, borderRight: `1px solid ${C.border}`,
          display: "flex", flexDirection: "column", backgroundColor: C.bgSub,
        }}>
          <div style={{ padding: "14px 12px 10px", borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text, letterSpacing: 0.5 }}>Voice::CC</div>
                <div style={{ fontSize: 11, color: C.textTer, marginTop: 1 }}>Claude Code</div>
              </div>
              <button onClick={() => setShowRail(false)} style={{
                background: "none", border: "none", cursor: "pointer", color: C.textTer,
                padding: 4, display: "flex", borderRadius: 6,
              }} title="Collapse sidebar">
                <PanelRightClose size={16} style={{ transform: "scaleX(-1)" }} />
              </button>
            </div>
            <button onClick={newSession} style={{
              width: "100%", padding: "8px 0", borderRadius: 8,
              border: "none", backgroundColor: C.text, color: C.bg,
              cursor: "pointer", fontSize: 12, fontFamily: sans, fontWeight: 500,
              display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
            }}>
              <Plus size={13} /> New session
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
            {/* Current session */}
            {sessionId && (
              <div style={{
                width: "100%", textAlign: "left", padding: "10px 10px", borderRadius: 8,
                display: "flex", alignItems: "center", gap: 10,
                backgroundColor: C.bg, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", marginBottom: 8,
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: connected ? C.success : C.textFaint,
                }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    Current
                  </div>
                  <div style={{ fontSize: 11, color: C.textTer }}>{messages.length} messages</div>
                </div>
              </div>
            )}

            {/* Session history */}
            {history.sessions.length > 0 && (
              <div style={{ fontSize: 11, fontWeight: 600, color: C.textTer, padding: "6px 10px 4px", textTransform: "uppercase", letterSpacing: 0.5 }}>
                History
              </div>
            )}
            {history.sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => resumeSession(s.id)}
                style={{
                  width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 8,
                  display: "flex", alignItems: "flex-start", gap: 10,
                  border: "none", cursor: "pointer", fontFamily: sans,
                  backgroundColor: s.id === sessionId ? C.bg : "transparent",
                  boxShadow: s.id === sessionId ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                  marginBottom: 1,
                }}
              >
                <span style={{
                  width: 6, height: 6, borderRadius: "50%", flexShrink: 0, marginTop: 5,
                  backgroundColor: s.id === sessionId ? C.success : C.textFaint,
                }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{
                    fontSize: 12, color: C.text, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontWeight: s.id === sessionId ? 600 : 400,
                  }}>
                    {s.preview}
                  </div>
                  <div style={{ fontSize: 11, color: C.textTer, marginTop: 1 }}>
                    {new Date(s.mtime * 1000).toLocaleDateString([], { month: "short", day: "numeric" })}
                    {" \u00b7 "}
                    {s.msg_count} msgs
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Connection status */}
          <div style={{ padding: "8px 12px", borderTop: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 6 }}>
            {connected ? <Wifi size={12} color={C.success} /> : <WifiOff size={12} color={C.danger} />}
            <span style={{ fontSize: 11, color: connected ? C.textTer : C.danger }}>{connected ? "Connected" : "Disconnected"}</span>
          </div>
        </div>
      )}

      {/* Main column */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Top bar */}
        <div style={{
          display: "flex", alignItems: "center", padding: "0 20px",
          height: 52, borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 12,
        }}>
          {!showRail && (
            <button onClick={() => setShowRail(true)} style={{
              background: "none", border: "none", cursor: "pointer",
              color: C.textTer, padding: 4, display: "flex", borderRadius: 6,
            }} title="Show sessions">
              <PanelRightOpen size={18} style={{ transform: "scaleX(-1)" }} />
            </button>
          )}

          <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>
            {sessionId ? `Session ${sessionId.slice(0, 8)}` : "New Session"}
          </span>

          <div style={{ flex: 1 }} />

          <VoiceDot state={voiceState} size={9} />
          <span style={{ fontSize: 13, color: voiceState === "off" ? C.textTer : C.textSec, minWidth: 70 }}>
            {voiceState === "off" ? "Mic off" : "Listening"}
          </span>

          <button onClick={toggleVoice} style={{
            width: 44, height: 44, borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", position: "relative", transition: "all 200ms",
            border: voice.listening ? `2px solid ${C.micOn}` : `2px solid ${C.textFaint}`,
            backgroundColor: voice.listening ? "#FEF2F2" : C.bg,
          }}>
            {voice.listening ? <Mic size={18} color={C.micOn} /> : <MicOff size={18} color={C.textTer} />}
            {voice.listening && (
              <div style={{
                position: "absolute", inset: -4, borderRadius: "50%",
                border: `2px solid ${C.micOn}`, opacity: 0.25,
                animation: "vcc-ring 2s ease-out infinite",
              }} />
            )}
          </button>

          <button onClick={tts.toggle} style={{
            background: "none", border: "none", cursor: "pointer",
            color: tts.enabled ? C.voice : C.textTer, padding: 6, display: "flex",
            borderRadius: 6,
          }} title={tts.enabled ? "Mute responses" : "Speak responses"}>
            {tts.enabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
          </button>

          <div style={{ width: 1, height: 24, backgroundColor: C.border, margin: "0 4px" }} />

          <button onClick={() => setShowDetail(!showDetail)} style={{
            background: "none", border: "none", cursor: "pointer",
            color: showDetail ? C.accentBlue : C.textTer, padding: 6, display: "flex",
            borderRadius: 6,
          }} title={showDetail ? "Hide detail panel" : "Show detail panel"}>
            {showDetail ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
          </button>
        </div>

        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {/* Transcript */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <div ref={scrollRef} style={{
              flex: 1, overflowY: "auto", padding: "24px 32px 100px",
              display: "flex", justifyContent: "center",
            }}>
              <div style={{ width: "100%", maxWidth: 720 }}>
                {messages.length === 0 && (
                  <div style={{
                    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                    height: "60vh", color: C.textTer, gap: 12, textAlign: "center",
                  }}>
                    <Terminal size={40} strokeWidth={1.2} />
                    <div style={{ fontSize: 16, fontWeight: 500, color: C.textSec }}>Voice::CC</div>
                    <div style={{ fontSize: 13, maxWidth: 400 }}>
                      Type a message below or click the mic button to start voice input.
                      {!voice.supported && <span style={{ display: "block", marginTop: 4, color: C.approval }}>Voice input not supported in this browser.</span>}
                    </div>
                  </div>
                )}
                <TranscriptView
                  messages={messages}
                  onSelectArtifact={handleSelectArtifact}
                  selectedArtifactId={detailId}
                  isMobile={false}
                  onApprove={approve}
                  onReject={reject}
                />
                {streaming && (
                  <div style={{ padding: "16px 0", display: "flex", alignItems: "center", gap: 8 }}>
                    <Loader2 size={14} color={C.textSec} style={{ animation: "spin 1s linear infinite" }} />
                    <span style={{ fontSize: 14, color: C.textSec }}>Working...</span>
                  </div>
                )}
                {voice.interim && (
                  <div style={{ padding: "12px 16px", color: C.textTer, fontStyle: "italic", fontSize: 14, backgroundColor: C.youBg, borderRadius: 8, borderLeft: `3px solid ${C.youBorder}` }}>
                    {voice.interim}
                  </div>
                )}
                {/* Scroll anchor */}
                <div ref={scrollAnchorRef} style={{ height: 1 }} />
              </div>
            </div>

            {/* Input */}
            <div style={{
              borderTop: `1px solid ${C.border}`, padding: "10px 32px",
              display: "flex", justifyContent: "center", backgroundColor: C.bg, flexShrink: 0,
            }}>
              <div style={{
                width: "100%", maxWidth: 720, display: "flex", alignItems: "center",
                border: `1px solid ${C.border}`, borderRadius: 12,
                padding: "0 16px", height: 44, backgroundColor: C.surface,
              }}>
                <span style={{ color: C.textTer, fontSize: 14, marginRight: 10, fontFamily: mono }}>{"\u276F"}</span>
                <input
                  value={inp} onChange={(e) => setInp(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
                  placeholder={voice.listening ? "Voice active \u2014 or type here" : "Type a message..."}
                  disabled={!connected}
                  style={{ flex: 1, backgroundColor: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14, fontFamily: sans }}
                />
              </div>
            </div>
          </div>

          {/* Detail panel */}
          {hasDetail && (
            <div style={{
              width: 420, flexShrink: 0, borderLeft: `1px solid ${C.border}`,
              backgroundColor: C.bg, display: "flex", flexDirection: "column",
            }}>
              <DetailPanel artifact={detailArtifact} onClose={() => { setDetailArtifact(null); setDetailId(null); }} />
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes vcc-ring { 0%{transform:scale(1);opacity:.35} 100%{transform:scale(1.8);opacity:0} }
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::placeholder { color: ${C.textFaint}; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
      `}</style>
    </div>
  );
}

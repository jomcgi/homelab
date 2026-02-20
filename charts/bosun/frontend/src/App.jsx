import { useState, useEffect, useRef, useCallback } from "react";
import {
  Mic, MicOff, Volume2, VolumeX, Terminal, Plus, PanelRightOpen, PanelRightClose,
  Wifi, WifiOff, Send, Grid,
} from "lucide-react";
import { C, sans, mono } from "./tokens.js";
import { useBreakpoint } from "./hooks/useBreakpoint.js";
import { useClaudeSocket } from "./hooks/useClaudeSocket.js";
import { useVoiceInput } from "./hooks/useVoiceInput.js";
import { useTTS, confirmTTS } from "./hooks/useTTS.js";
import { useVoiceCommands } from "./hooks/useVoiceCommands.js";
import { useSessionHistory } from "./hooks/useSessionHistory.js";
import { useResizable } from "./hooks/useResizable.js";
import { useSessionArtifacts } from "./hooks/useSessionArtifacts.js";
import { VoiceDot } from "./components/VoiceDot.jsx";
import { DetailPanel } from "./components/DetailPanel.jsx";
import { TranscriptView } from "./components/TranscriptView.jsx";
import { ActionChips } from "./components/ActionChips.jsx";

// ── Shared styles (used by both mobile and desktop layouts) ────────────────
const sharedCSS = `
  @keyframes vcc-ring { 0%{transform:scale(1);opacity:.35} 100%{transform:scale(1.8);opacity:0} }
  @keyframes vcc-wake { 0%{transform:scale(1);opacity:.8} 50%{transform:scale(1.5);opacity:.5} 100%{transform:scale(2);opacity:0} }
  @keyframes vcc-pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  @keyframes vcc-bounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }
  @media (prefers-reduced-motion: reduce) {
    .vcc-animated { animation: none !important; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  input::placeholder { color: ${C.textFaint}; }
  .vcc-markdown h1, .vcc-markdown h2, .vcc-markdown h3, .vcc-markdown h4 {
    color: ${C.text}; margin: 12px 0 6px; line-height: 1.3;
  }
  .vcc-markdown h1 { font-size: 18px; font-weight: 700; }
  .vcc-markdown h2 { font-size: 16px; font-weight: 600; }
  .vcc-markdown h3 { font-size: 14px; font-weight: 600; }
  .vcc-markdown p { margin: 6px 0; }
  .vcc-markdown code {
    font-family: ${mono}; font-size: 12px; background: ${C.surface};
    padding: 2px 5px; border-radius: 4px; color: ${C.text};
  }
  .vcc-markdown pre {
    background: ${C.surface}; border: 1px solid ${C.border}; border-radius: 8px;
    padding: 12px; margin: 8px 0; overflow-x: auto;
  }
  .vcc-markdown pre code { background: none; padding: 0; font-size: 12px; line-height: 1.6; }
  .vcc-markdown ul, .vcc-markdown ol { padding-left: 20px; margin: 6px 0; }
  .vcc-markdown li { margin: 3px 0; }
  .vcc-markdown blockquote {
    border-left: 3px solid ${C.border}; padding: 4px 12px; margin: 8px 0;
    color: ${C.textSec}; font-style: italic;
  }
  .vcc-markdown a { color: ${C.accentBlue}; text-decoration: none; }
  .vcc-markdown a:hover { text-decoration: underline; }
  .vcc-markdown table { border-collapse: collapse; margin: 8px 0; width: 100%; }
  .vcc-markdown th, .vcc-markdown td {
    border: 1px solid ${C.border}; padding: 6px 10px; font-size: 13px; text-align: left;
  }
  .vcc-markdown th { background: ${C.surface}; font-weight: 600; }
  .vcc-markdown hr { border: none; border-top: 1px solid ${C.border}; margin: 12px 0; }
  .vcc-markdown img { max-width: 100%; border-radius: 6px; }
  .vcc-copy-trigger .vcc-copy-btn { opacity: 0; transition: opacity 150ms; }
  .vcc-copy-trigger:hover .vcc-copy-btn { opacity: 1; }
  .vcc-code-block { position: relative; }
  .vcc-code-copy {
    position: absolute; top: 8px; right: 8px;
    padding: 2px 8px; border-radius: 4px;
    border: 1px solid ${C.border}; background: ${C.bg};
    font-size: 10px; cursor: pointer; color: ${C.textSec};
    opacity: 0; transition: opacity 150ms;
  }
  .vcc-code-block:hover .vcc-code-copy { opacity: 1; }
`;

// ── Helpers ────────────────────────────────────────────────────────────────

function relativeTime(epochSecs) {
  const delta = Math.floor(Date.now() / 1000) - epochSecs;
  if (delta < 60) return "now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h`;
  if (delta < 604800) return `${Math.floor(delta / 86400)}d`;
  return `${Math.floor(delta / 604800)}w`;
}

// ── Main App ───────────────────────────────────────────────────────────────

export default function App() {
  const bp = useBreakpoint();
  const tts = useTTS();
  const { connected, sessionId, messages, streaming, pendingApproval, send, approve, reject, newSession, resumeSession, wsRef, addGeminiMessage } = useClaudeSocket({
    onResult: (text) => {
      // Dedup: skip if this is the same result text as last time (echo/replay)
      if (text === lastTtsRef.current) return;
      lastTtsRef.current = text;

      // Voice already suppressed via streaming effect, but ensure it's off
      voice.suppress();

      // Stream TTS: first sentence audio arrives while rest is still generating
      (async () => {
        try {
          const res = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, summarize: true, suggest_actions: true, stream: true }),
          });

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          const audioChunks = [];  // collected for replay blob
          const audioQueue = [];   // pending Audio objects to play sequentially
          let playing = false;

          const playNext = () => {
            if (audioQueue.length === 0) { playing = false; voice.unsuppress(); return; }
            playing = true;
            const a = audioQueue.shift();
            a.onended = () => { URL.revokeObjectURL(a.src); playNext(); };
            a.play().catch(() => { URL.revokeObjectURL(a.src); playNext(); });
          };

          const enqueueAudio = (b64, mimeType) => {
            const raw = atob(b64);
            const bytes = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
            const blob = new Blob([bytes], { type: mimeType || "audio/wav" });
            audioChunks.push(blob);
            if (tts.enabled) {
              const a = new Audio(URL.createObjectURL(blob));
              audioQueue.push(a);
              if (!playing) playNext();
            }
          };

          // Read NDJSON stream
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            while (buffer.includes("\n")) {
              const idx = buffer.indexOf("\n");
              const line = buffer.slice(0, idx).trim();
              buffer = buffer.slice(idx + 1);
              if (!line) continue;
              const chunk = JSON.parse(line);
              if (chunk.audio) enqueueAudio(chunk.audio, chunk.mime_type);
              if (chunk.done) {
                if (chunk.summary) {
                  addGeminiMessage(chunk.summary);
                  if (sessionId) {
                    fetch("/api/summaries", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ session_id: sessionId, msg_id: `tts-${Date.now()}`, text: chunk.summary }),
                    }).catch(() => {});
                  }
                }
                if (chunk.actions?.length) voiceCommands.setActions(chunk.actions);
              }
            }
          }

          // Save combined audio for replay
          if (audioChunks.length > 0) {
            voiceCommands.saveLastAudio(new Blob(audioChunks, { type: "audio/wav" }));
          }

          // If no audio was queued (TTS disabled or failed), unsuppress now
          if (!playing) voice.unsuppress();
        } catch {
          voice.unsuppress();
          tts.speak(text);
        }
      })();
    },
  });
  const voice = useVoiceInput();
  const voiceCommands = useVoiceCommands({
    send, newSession, wsRef, tts, streaming, pendingApproval, approve, reject,
  });
  const history = useSessionHistory();
  const panelResize = useResizable({ initialWidth: 420, minWidth: 280, maxWidth: 900 });
  const allArtifacts = useSessionArtifacts(messages);
  const [inp, setInp] = useState("");
  const [detailArtifact, setDetailArtifact] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [showDetail, setShowDetail] = useState(true);
  const [showRail, setShowRail] = useState(true);
  const scrollRef = useRef(null);
  const scrollAnchorRef = useRef(null);
  const lastTtsRef = useRef("");  // Dedup guard for repeated results

  // Suppress voice recognition while Claude is working to prevent echo getting queued
  useEffect(() => {
    if (streaming) voice.suppress();
  }, [streaming]); // eslint-disable-line react-hooks/exhaustive-deps

  // Adaptive debounce: shorter silence window during approval state for snappy "yes"/"go ahead"
  useEffect(() => {
    voice.setFastDebounce(!!pendingApproval);
  }, [pendingApproval]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load session from URL param on mount — always load messages for URL sessions
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlSession = params.get("session");
    if (urlSession) {
      // Force-load even if sessionId matches (page refresh case)
      resumeSession(urlSession, /* force */ true);
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
      voiceCommands.clearActions(); // Clear stale action chips
      voice.start(
        // onResult — route through voice command classifier instead of direct send
        async (text) => {
          const result = await voiceCommands.classify(text);
          // Handle switch_session command result
          if (result?.switchTo) {
            resumeSession(result.switchTo);
          }
        },
        // Wake word callbacks
        {
          onWakeWord: (text) => voiceCommands.classify(text),
          onCompact: (directive) => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "compact", message: directive }));
            }
            confirmTTS("Compacting session context");
          },
        },
      ).catch((err) => {
        console.warn("Voice start failed:", err);
      });
    }
  };

  const handleSelectArtifact = useCallback((artifact, id) => {
    if (detailId === id) { setDetailArtifact(null); setDetailId(null); }
    else { setDetailArtifact(artifact); setDetailId(id); setShowDetail(true); }
  }, [detailId]);

  const openGallery = useCallback(() => {
    setDetailArtifact(null);
    setDetailId(null);
    setShowDetail(true);
  }, []);

  // ── Mobile layout ──────────────────────────────────────────────
  if (bp === "mobile") {
    return (
      <div style={{ width: "100vw", height: "100dvh", backgroundColor: C.bg, fontFamily: sans, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "0 12px", height: 52, borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 8, backgroundColor: C.surface }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Bosun</span>
            {connected ? <Wifi size={12} color={C.success} /> : <WifiOff size={12} color={C.danger} />}
          </div>
          <VoiceDot state={voiceState} size={8} />
          {voice.listening && <span style={{ fontSize: 12, color: C.textSec }}>Listening</span>}
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "16px 12px 120px" }}>
          <TranscriptView messages={messages} onSelectArtifact={() => {}} selectedArtifactId={null} isMobile onApprove={approve} onReject={reject} actions={voiceCommands.actions} onAction={(prompt) => { voiceCommands.clearActions(); send(prompt); }} />
          {voiceCommands.actions.length > 0 && !messages.some((m) => m.role === "gemini") && (
            <div style={{ marginBottom: 12, padding: "0 4px" }}>
              <ActionChips actions={voiceCommands.actions} onAction={(prompt) => { voiceCommands.clearActions(); send(prompt); }} />
            </div>
          )}
          {streaming && (
            <div role="status" aria-live="polite" style={{ padding: "12px 0", display: "flex", alignItems: "center", gap: 6 }}>
              {[0, 1, 2].map((i) => (
                <span key={i} className="vcc-animated" style={{
                  width: 4, height: 4, borderRadius: "50%", backgroundColor: C.textTer,
                  animation: `vcc-bounce 0.6s ease-in-out ${i * 0.15}s infinite`,
                  animationFillMode: "both",
                }} />
              ))}
              <span style={{ fontSize: 13, color: C.textTer, fontFamily: mono }}>working</span>
            </div>
          )}
          {(voice.pending || voice.interim) && (
            <div style={{ padding: "8px 12px", color: C.textTer, fontStyle: "italic", fontSize: 14 }}>
              {voice.pending && <span style={{ color: C.textSec }}>{voice.pending} </span>}
              {voice.interim}
            </div>
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

        <style>{sharedCSS}</style>
      </div>
    );
  }

  // ── Desktop layout ─────────────────────────────────────────────
  const hasDetail = showDetail && (detailArtifact || allArtifacts.length > 0);

  return (
    <div style={{ width: "100vw", height: "100dvh", backgroundColor: C.bg, fontFamily: sans, display: "flex", overflow: "hidden" }}>

      {/* Sessions rail */}
      {showRail && (
        <div style={{
          width: 220, flexShrink: 0, borderRight: `1px solid ${C.border}`,
          display: "flex", flexDirection: "column", backgroundColor: C.bgSub,
        }}>
          <div style={{ padding: "14px 12px 10px", borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text, letterSpacing: 0.5 }}>Bosun</div>
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
                  boxShadow: connected ? `0 0 6px ${C.success}` : "none",
                  transition: "box-shadow 300ms",
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
            {history.sessions.map((s) => {
              const isActive = s.id === sessionId;
              return (
                <button
                  key={s.id}
                  onClick={() => resumeSession(s.id)}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = C.surfaceHover; }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = "transparent"; }}
                  style={{
                    width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 8,
                    display: "flex", alignItems: "flex-start", gap: 10,
                    border: "none", cursor: "pointer", fontFamily: sans,
                    backgroundColor: isActive ? C.bg : "transparent",
                    boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                    marginBottom: 1, transition: "background-color 150ms",
                  }}
                >
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%", flexShrink: 0, marginTop: 5,
                    backgroundColor: isActive ? C.success : C.textFaint,
                  }} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{
                      fontSize: 12, color: C.text, overflow: "hidden",
                      textOverflow: "ellipsis", whiteSpace: "nowrap",
                      fontWeight: isActive ? 600 : 400,
                    }}>
                      {s.preview}
                    </div>
                    <div style={{ fontSize: 11, color: C.textTer, marginTop: 1 }}>
                      {relativeTime(s.mtime)}
                      {" \u00b7 "}
                      {s.msg_count} msgs
                      {s.project && (
                        <span style={{ display: "block", fontSize: 10, color: C.textFaint, marginTop: 1, fontFamily: mono, opacity: 0.7 }}>
                          {s.project.split("/").slice(-2).join("/")}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Connection status */}
          <div style={{ padding: "8px 12px", borderTop: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 6 }}>
            {connected ? <Wifi size={12} color={C.success} /> : <WifiOff size={12} color={C.danger} />}
            <span style={{ fontSize: 11, fontFamily: mono, color: connected ? C.textTer : C.danger }}>{connected ? "connected" : "reconnecting\u2026"}</span>
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
            border: voice.wakeWordFlash
              ? `2px solid ${C.voice}`
              : voice.listening ? `2px solid ${C.micOn}` : `2px solid ${C.textFaint}`,
            backgroundColor: voice.wakeWordFlash
              ? C.voiceBg
              : voice.listening ? "#FEF2F2" : C.bg,
          }}>
            {voice.listening ? <Mic size={18} color={voice.wakeWordFlash ? C.voice : C.micOn} /> : <MicOff size={18} color={C.textTer} />}
            {voice.listening && (
              <div style={{
                position: "absolute", inset: -4, borderRadius: "50%",
                border: `2px solid ${voice.wakeWordFlash ? C.voice : C.micOn}`,
                opacity: voice.wakeWordFlash ? 0.6 : 0.25,
                animation: voice.wakeWordFlash ? "vcc-wake 0.6s ease-out" : "vcc-ring 2s ease-out infinite",
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

          <button onClick={openGallery} style={{
            background: "none", border: "none", cursor: "pointer",
            color: allArtifacts.length > 0 ? C.textSec : C.textFaint, padding: 6, display: "flex",
            borderRadius: 6, position: "relative",
          }} title="Artifact gallery">
            <Grid size={18} />
            {allArtifacts.length > 0 && (
              <span style={{
                position: "absolute", top: 2, right: 2, width: 14, height: 14,
                borderRadius: "50%", backgroundColor: C.accentBlue, color: "#fff",
                fontSize: 9, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
                fontFamily: sans,
              }}>{allArtifacts.length}</span>
            )}
          </button>

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
                    <div style={{ fontSize: 16, fontWeight: 500, color: C.textSec }}>Bosun</div>
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
                  actions={voiceCommands.actions}
                  onAction={(prompt) => { voiceCommands.clearActions(); send(prompt); }}
                />
                {/* Fallback: render action chips outside transcript if no summary group picked them up */}
                {voiceCommands.actions.length > 0 && !messages.some((m) => m.role === "gemini") && (
                  <div style={{ marginBottom: 16 }}>
                    <ActionChips actions={voiceCommands.actions} onAction={(prompt) => { voiceCommands.clearActions(); send(prompt); }} />
                  </div>
                )}
                {streaming && (
                  <div role="status" aria-live="polite" style={{ padding: "16px 0", display: "flex", alignItems: "center", gap: 6 }}>
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="vcc-animated" style={{
                        width: 5, height: 5, borderRadius: "50%", backgroundColor: C.textTer,
                        animation: `vcc-bounce 0.6s ease-in-out ${i * 0.15}s infinite`,
                        animationFillMode: "both",
                      }} />
                    ))}
                    <span style={{ fontSize: 14, color: C.textTer, fontFamily: mono, marginLeft: 2 }}>working</span>
                  </div>
                )}
                {(voice.pending || voice.interim) && (
                  <div style={{ padding: "12px 16px", color: C.textTer, fontStyle: "italic", fontSize: 14, backgroundColor: C.youBg, borderRadius: 8, borderLeft: `3px solid ${C.youBorder}` }}>
                    {voice.pending && <span style={{ color: C.textSec }}>{voice.pending} </span>}
                    {voice.interim}
                    {voice.pending && !voice.interim && (
                      <span style={{ fontSize: 11, color: C.textTer, marginLeft: 8 }}>sending in 2s...</span>
                    )}
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
                padding: "0 6px 0 16px", height: 44, backgroundColor: C.surface,
              }}>
                <span style={{ color: C.textTer, fontSize: 14, marginRight: 10, fontFamily: mono }}>{"\u276F"}</span>
                <input
                  value={inp} onChange={(e) => setInp(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
                  placeholder={voice.listening ? "Voice active \u2014 or type here" : "Type a message..."}
                  disabled={!connected}
                  style={{ flex: 1, backgroundColor: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14, fontFamily: sans }}
                />
                <button
                  onMouseDown={(e) => { e.preventDefault(); handleSubmit(); }}
                  tabIndex={-1}
                  style={{
                    width: 32, height: 32, borderRadius: 8, border: "none", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                    backgroundColor: inp.trim() ? C.text : "transparent",
                    color: inp.trim() ? C.bg : "transparent",
                    opacity: inp.trim() ? 1 : 0,
                    transition: "opacity 150ms, background-color 150ms",
                    pointerEvents: inp.trim() ? "auto" : "none",
                  }}
                >
                  <Send size={14} />
                </button>
              </div>
            </div>
          </div>

          {/* Detail panel */}
          {hasDetail && (
            <div style={{
              width: panelResize.width, flexShrink: 0, borderLeft: `1px solid ${C.border}`,
              backgroundColor: C.bg, display: "flex", flexDirection: "column", position: "relative",
            }}>
              {/* Drag handle */}
              <div
                onMouseDown={panelResize.onMouseDown}
                style={{
                  position: "absolute", left: 0, top: 0, bottom: 0, width: 6,
                  cursor: "col-resize", zIndex: 10,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = C.border; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
              />
              <DetailPanel
                artifact={detailArtifact}
                onClose={() => { setDetailArtifact(null); setDetailId(null); setShowDetail(false); }}
                allArtifacts={allArtifacts}
                onSelectArtifact={handleSelectArtifact}
              />
            </div>
          )}
        </div>
      </div>

      <style>{sharedCSS + `
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: ${C.borderStrong}; }
      `}</style>
    </div>
  );
}

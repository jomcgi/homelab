import { useEffect, useCallback } from "react";
import { X } from "lucide-react";
import { C, sans, mono } from "../tokens.js";

// ── Help overlay for voice commands & UI markers ─────────────────────────

const Q = (s) => `\u201C${s}\u201D`; // wrap in curly quotes for display

const SECTIONS = [
  {
    title: "Quick Commands",
    description: "Say these phrases exactly \u2014 they\u2019re matched instantly on-device.",
    items: [
      { phrases: [Q("new session"), Q("start over"), Q("fresh start")], action: "Start a new session" },
      { phrases: [Q("cancel"), Q("stop"), Q("nevermind")], action: "Cancel the current task" },
      { phrases: [Q("approve"), Q("yes"), Q("do it"), Q("go ahead")], action: "Approve a pending action" },
      { phrases: [Q("reject"), Q("no"), Q("don\u2019t"), Q("nope")], action: "Reject a pending action" },
      { phrases: [Q("mute"), Q("be quiet")], action: "Mute spoken responses" },
      { phrases: [Q("unmute"), Q("speak"), Q("talk to me")], action: "Unmute spoken responses" },
      { phrases: [Q("say that again"), Q("repeat")], action: "Replay the last response" },
      { phrases: [Q("what\u2019s happening"), Q("are you busy")], action: "Check if Claude is working" },
    ],
  },
  {
    title: "Smart Commands",
    description: "Shorter phrases are classified by Gemini. Longer messages (20+ words) go straight to Claude.",
    items: [
      { phrases: [Q("list my sessions")], action: "List the 3 most recent sessions" },
      { phrases: [Q("go back to the auth one")], action: "Fuzzy-search and switch session" },
    ],
  },
  {
    title: "Wake Word",
    description: `Prefix with ${Q("Hey Claude")} to skip the silence timer and send immediately.`,
    items: [
      { phrases: [Q("Hey Claude, check the logs")], action: "Sends instantly (no 800ms wait)" },
      { phrases: [Q("Hey Claude compact [reason]")], action: "Compress session context" },
    ],
  },
];

const MARKERS = [
  { color: C.you, bg: C.youBg, border: C.youBorder, label: "Your messages" },
  { color: C.voice, bg: C.voiceBg, border: C.voiceBorder, label: "Voice / TTS summaries" },
  { color: C.approval, bg: C.approvalBg, border: C.approvalBorder, label: "Pending approval" },
  { color: C.micOn, bg: "#FEF2F2", border: "#FECACA", label: "Mic active" },
];

const KBD_STYLE = {
  display: "inline-block",
  padding: "1px 6px",
  borderRadius: 4,
  border: `1px solid ${C.border}`,
  backgroundColor: C.surface,
  fontFamily: mono,
  fontSize: 11,
  lineHeight: "18px",
  color: C.textSec,
};

export function HelpOverlay({ open, onClose }) {
  // Close on Escape
  const handleKey = useCallback(
    (e) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.25)",
          zIndex: 9998,
          animation: "helpFadeIn 150ms ease-out",
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: "fixed",
          bottom: 72,
          right: 24,
          width: 420,
          maxHeight: "calc(100dvh - 120px)",
          overflowY: "auto",
          backgroundColor: C.bg,
          borderRadius: 14,
          boxShadow: "0 12px 40px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.08)",
          zIndex: 9999,
          fontFamily: sans,
          animation: "helpSlideUp 200ms ease-out",
        }}
      >
        {/* Header */}
        <div
          style={{
            position: "sticky",
            top: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px 12px",
            borderBottom: `1px solid ${C.border}`,
            backgroundColor: C.bg,
            borderRadius: "14px 14px 0 0",
            zIndex: 1,
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>
              Voice Commands & Markers
            </div>
            <div style={{ fontSize: 12, color: C.textTer, marginTop: 2 }}>
              <span style={KBD_STYLE}>⌘</span>{" "}
              <span style={KBD_STYLE}>?</span>{" "}
              to toggle
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: C.textTer,
              padding: 4,
              display: "flex",
              borderRadius: 6,
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: "16px 20px 20px" }}>
          {/* Color markers */}
          <div style={{ marginBottom: 20 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: C.textTer,
                textTransform: "uppercase",
                letterSpacing: 0.5,
                marginBottom: 8,
              }}
            >
              Color Indicators
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {MARKERS.map((m) => (
                <div
                  key={m.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 10px",
                    borderRadius: 6,
                    backgroundColor: m.bg,
                    border: `1px solid ${m.border}`,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor: m.color,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontSize: 12, color: C.text }}>{m.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Command sections */}
          {SECTIONS.map((section) => (
            <div key={section.title} style={{ marginBottom: 18 }}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: C.textTer,
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  marginBottom: 4,
                }}
              >
                {section.title}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: C.textTer,
                  marginBottom: 8,
                  lineHeight: 1.4,
                }}
              >
                {section.description}
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                {section.items.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      gap: 10,
                      padding: "6px 10px",
                      borderRadius: 6,
                      backgroundColor: C.surface,
                    }}
                  >
                    <div
                      style={{
                        flex: 1,
                        fontSize: 12,
                        fontFamily: mono,
                        color: C.voice,
                        lineHeight: 1.5,
                      }}
                    >
                      {item.phrases.join("  ")}
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: C.textSec,
                        whiteSpace: "nowrap",
                        flexShrink: 0,
                      }}
                    >
                      {item.action}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Timing note */}
          <div
            style={{
              fontSize: 12,
              color: C.textTer,
              lineHeight: 1.5,
              padding: "10px 12px",
              borderRadius: 6,
              backgroundColor: C.surface,
              border: `1px solid ${C.borderLight}`,
            }}
          >
            <strong style={{ color: C.textSec }}>Timing:</strong> Voice input
            waits <span style={KBD_STYLE}>800ms</span> of silence before
            sending. During approval prompts this drops to{" "}
            <span style={KBD_STYLE}>400ms</span> for snappy yes/no responses.
          </div>
        </div>
      </div>

      <style>{`
        @keyframes helpFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes helpSlideUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </>
  );
}

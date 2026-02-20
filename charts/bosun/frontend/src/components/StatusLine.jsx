import { useState, useEffect } from "react";
import { C, mono } from "../tokens.js";

function formatElapsed(ms) {
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return `${mins}m ${rem.toString().padStart(2, "0")}s`;
}

export function StatusLine({ streaming, turnStart, usage, todos }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!streaming || !turnStart) {
      setElapsed(0);
      return;
    }
    setElapsed(Date.now() - turnStart);
    const id = setInterval(() => setElapsed(Date.now() - turnStart), 1000);
    return () => clearInterval(id);
  }, [streaming, turnStart]);

  if (!streaming) return null;

  // Find the active (in_progress) todo's activeForm text for display
  const activeTodo = (todos || []).find((t) => t.status === "in_progress");
  const statusText = activeTodo?.activeForm || "Working...";

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        padding: "16px 0",
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontFamily: mono,
        fontSize: 13,
        color: C.textTer,
      }}
    >
      {/* Animated pulse prefix */}
      <span
        className="vcc-animated"
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: C.accentBlue,
          animation: "vcc-pulse 1.5s ease-in-out infinite",
          flexShrink: 0,
        }}
      />

      {/* Active status text */}
      <span style={{ color: C.textSec }}>{statusText}</span>

      {/* Elapsed time */}
      {turnStart && (
        <span style={{ color: C.textFaint }}>{formatElapsed(elapsed)}</span>
      )}

      {/* Token count */}
      {usage && usage.output_tokens > 0 && (
        <span style={{ color: C.textFaint }}>
          {(usage.output_tokens / 1000).toFixed(1)}k tokens
        </span>
      )}
    </div>
  );
}

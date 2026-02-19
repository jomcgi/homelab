import { useState, useCallback } from "react";
import { C, sans } from "../tokens.js";

export function CopyButton({ getText }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async (e) => {
    e.stopPropagation();
    const text = typeof getText === "function" ? getText() : getText;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.warn("Copy failed:", err);
    }
  }, [getText]);

  return (
    <button
      className="vcc-copy-btn"
      onClick={handleCopy}
      style={{
        position: "absolute", top: 8, right: 8,
        padding: "2px 8px", borderRadius: 4,
        border: `1px solid ${C.border}`, background: C.bg,
        fontSize: 10, cursor: "pointer", color: C.textSec,
        fontFamily: sans, zIndex: 1,
        opacity: 0, transition: "opacity 150ms",
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

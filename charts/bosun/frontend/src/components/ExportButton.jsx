import { useState, useCallback, useRef, useEffect } from "react";
import { Download, Copy, FileDown } from "lucide-react";
import { C, sans } from "../tokens.js";
import { formatMarkdown } from "../utils/exportMarkdown.js";

export function ExportButton({ messages, sessionId }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const menuRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const getMarkdown = useCallback(() => {
    return formatMarkdown(messages, sessionId);
  }, [messages, sessionId]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(getMarkdown());
      setCopied(true);
      setTimeout(() => { setCopied(false); setOpen(false); }, 1200);
    } catch (err) {
      console.warn("Copy failed:", err);
    }
  }, [getMarkdown]);

  const handleDownload = useCallback(() => {
    const md = getMarkdown();
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ts = new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-");
    a.download = `bosun-${sessionId ? sessionId.slice(0, 8) : "session"}-${ts}.md`;
    a.click();
    URL.revokeObjectURL(url);
    setOpen(false);
  }, [getMarkdown, sessionId]);

  if (!messages || messages.length === 0) return null;

  return (
    <div ref={menuRef} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "none", border: "none", cursor: "pointer",
          color: C.textSec, padding: 6, display: "flex", borderRadius: 6,
        }}
        title="Export transcript"
      >
        <Download size={18} />
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "100%", right: 0, marginTop: 4,
          backgroundColor: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 8, padding: 4, minWidth: 170, zIndex: 100,
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
        }}>
          <button onClick={handleCopy} style={{
            display: "flex", alignItems: "center", gap: 8,
            width: "100%", padding: "8px 12px", borderRadius: 6,
            background: "none", border: "none", cursor: "pointer",
            fontFamily: sans, fontSize: 13, color: C.text,
            textAlign: "left",
          }}>
            <Copy size={14} />
            {copied ? "Copied!" : "Copy to clipboard"}
          </button>
          <button onClick={handleDownload} style={{
            display: "flex", alignItems: "center", gap: 8,
            width: "100%", padding: "8px 12px", borderRadius: 6,
            background: "none", border: "none", cursor: "pointer",
            fontFamily: sans, fontSize: 13, color: C.text,
            textAlign: "left",
          }}>
            <FileDown size={14} />
            Download .md
          </button>
        </div>
      )}
    </div>
  );
}

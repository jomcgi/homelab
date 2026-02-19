import { useState } from "react";
import { ChevronUp, ChevronDown, ChevronRight } from "lucide-react";
import { C, sans, mono } from "../tokens.js";
import { MermaidDiagram } from "./MermaidDiagram.jsx";
import { CopyButton } from "./CopyButton.jsx";
import { artifactIcon } from "../artifactIcons.js";

export function InlineArtifact({ artifact, onOpen }) {
  const [open, setOpen] = useState(false);
  const Icon = artifactIcon(artifact || {});
  if (!artifact) return null;

  // ── Compact mode (desktop with onOpen): image thumbnail card ──
  if (onOpen && artifact.type === "image") {
    return (
      <button onClick={() => onOpen(artifact)} style={{
        display: "inline-flex", alignItems: "center", gap: 10,
        padding: "6px 10px", marginTop: 6, marginRight: 6,
        border: `1px solid ${C.border}`, borderRadius: 8,
        backgroundColor: C.surface, cursor: "pointer", fontFamily: sans,
        transition: "all 150ms",
      }}>
        <img
          src={`data:${artifact.mimeType || "image/png"};base64,${artifact.data}`}
          alt={artifact.label}
          style={{ width: 60, height: 60, objectFit: "cover", borderRadius: 4 }}
        />
        <div style={{ textAlign: "left" }}>
          <div style={{ fontSize: 12, color: C.text, fontWeight: 500 }}>{artifact.label}</div>
          <div style={{ fontSize: 11, color: C.textTer, display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
            <ChevronRight size={11} /> Click to expand
          </div>
        </div>
      </button>
    );
  }

  // ── Compact mode (desktop with onOpen): mermaid pill ──
  if (onOpen && artifact.type === "mermaid") {
    return (
      <button onClick={() => onOpen(artifact)} style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "5px 12px", marginTop: 6, marginRight: 6,
        border: `1px solid ${C.border}`, borderRadius: 20,
        backgroundColor: C.surface, cursor: "pointer", fontFamily: sans,
        fontSize: 12, color: C.textSec, transition: "all 150ms",
      }}>
        <Icon size={13} />
        <span>{artifact.label}</span>
        <span style={{ color: C.textTer, fontSize: 11 }}>diagram</span>
      </button>
    );
  }

  // ── Full inline rendering (mobile, or diff/output types) ──

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
            <Icon size={13} />
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
          <Icon size={13} /> {artifact.label}
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
          borderBottom: `1px solid ${C.border}`, cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><Icon size={13} /> {artifact.label}</span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <div style={{ position: "relative" }}>
          <CopyButton getText={() => artifact.data} />
          <div style={{ maxHeight: open ? "none" : 200, overflow: "hidden" }}>
            <MermaidDiagram code={artifact.data} id={artifact.label} />
          </div>
        </div>
      </div>
    );
  }
  if (artifact.type === "image") {
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <button onClick={() => setOpen(!open)} style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px 12px", backgroundColor: C.surface, border: "none",
          borderBottom: `1px solid ${C.border}`, cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><Icon size={13} /> {artifact.label}</span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <div style={{ maxHeight: open ? "none" : 200, overflow: "hidden", display: "flex", justifyContent: "center", padding: 8 }}>
          <img
            src={`data:${artifact.mimeType || "image/png"};base64,${artifact.data}`}
            alt={artifact.label}
            style={{ maxWidth: "100%", maxHeight: open ? "none" : 180, objectFit: "contain", borderRadius: 4 }}
          />
        </div>
      </div>
    );
  }
  return null;
}

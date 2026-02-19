import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { C, mono } from "../tokens.js";

// ── MermaidDiagram component (lazy-loads mermaid) ──────────────────────────
let mermaidReady = null; // shared promise for lazy init

function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "strict",
      });
      return mod.default;
    });
  }
  return mermaidReady;
}

export function MermaidDiagram({ code, id }) {
  const [svg, setSvg] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSvg(null);

    loadMermaid()
      .then(async (mermaid) => {
        if (cancelled) return;
        const graphId = `mermaid-${id || Math.random().toString(36).slice(2)}`;
        const { svg: rendered } = await mermaid.render(graphId, code);
        if (!cancelled) {
          setSvg(rendered);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || "Diagram syntax error");
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [code, id]);

  if (loading) {
    return (
      <div style={{ padding: "16px", display: "flex", alignItems: "center", gap: 8, color: C.textTer }}>
        <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
        <span style={{ fontSize: 12 }}>Rendering diagram...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div style={{ padding: "8px 12px", fontSize: 11, color: C.approval, backgroundColor: C.approvalBg, borderRadius: 4, marginBottom: 4 }}>
          Diagram error: {error}
        </div>
        <pre style={{ padding: "8px 12px", margin: 0, fontFamily: mono, fontSize: 11, lineHeight: 1.5, color: C.textSec, overflowX: "auto" }}>{code}</pre>
      </div>
    );
  }

  return (
    <div
      dangerouslySetInnerHTML={{ __html: svg }}
      style={{ padding: "12px", overflowX: "auto", display: "flex", justifyContent: "center" }}
    />
  );
}

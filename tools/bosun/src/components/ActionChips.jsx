import { C, sans } from "../tokens.js";

export function ActionChips({ actions, onAction }) {
  if (!actions?.length) return null;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
      {actions.map((a, i) => (
        <button key={i} onClick={() => onAction(a.prompt)} style={{
          padding: "6px 14px", borderRadius: 20,
          border: `1px solid ${C.voiceBorder}`, backgroundColor: C.voiceBg,
          color: C.voice, fontSize: 13, cursor: "pointer",
          fontFamily: sans, fontWeight: 500,
          transition: "all 150ms",
        }}
        onMouseEnter={(e) => { e.target.style.backgroundColor = C.voiceBorder; }}
        onMouseLeave={(e) => { e.target.style.backgroundColor = C.voiceBg; }}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}

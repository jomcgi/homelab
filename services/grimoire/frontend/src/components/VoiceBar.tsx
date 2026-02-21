import { C } from "@/lib/tokens";
import { Pill } from "./Pill";
import { useStore } from "@/lib/store";
import type { Player } from "@/types";

export function VoiceBar() {
  const players = useStore((s) => s.players);
  const speakingIds = useStore((s) => s.speakingIds);
  const connected = useStore((s) => s.connected);

  return (
    <div
      style={{
        padding: "6px 20px",
        background: C.gcpBg,
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: connected ? C.ok : C.warn, fontSize: 8 }}>
            {"\u25CF"}
          </span>
          <span
            style={{
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              color: C.fgMuted,
            }}
          >
            {connected ? "Voice Connected" : "Reconnecting..."}
          </span>
        </div>
        <span style={{ color: C.border }}>|</span>
        <div style={{ display: "flex", gap: 8 }}>
          {players.map((p: Player) => {
            const isSpeaking = speakingIds.includes(p.id);
            return (
              <div
                key={p.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <div
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: isSpeaking ? p.color : C.bgMuted,
                    border: `1.5px solid ${p.color}`,
                    boxShadow: isSpeaking ? `0 0 6px ${p.color}50` : "none",
                  }}
                />
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 12,
                    color: isSpeaking ? p.color : C.fgDim,
                    fontWeight: isSpeaking ? 600 : 400,
                  }}
                >
                  {p.name}
                </span>
              </div>
            );
          })}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: C.bgMuted,
                border: `1.5px solid ${C.warn}`,
              }}
            />
            <span style={{ fontFamily: C.sans, fontSize: 12, color: C.fgDim }}>
              DM
            </span>
          </div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Pill color={C.gcp} bg={`${C.gcp}15`}>
          Gemini Live
        </Pill>
        <Pill color={C.fgDim} bg={C.bgMuted}>
          Firestore RAG
        </Pill>
        <span style={{ fontFamily: C.mono, fontSize: 11, color: C.fgDim }}>
          ~280ms
        </span>
      </div>
    </div>
  );
}

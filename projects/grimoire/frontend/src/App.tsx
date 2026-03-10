import { useState } from "react";
import { C } from "@/lib/tokens";
import { useStore } from "@/lib/store";
import { useWebSocket } from "@/hooks/useWebSocket";
import { TabBar } from "@/components/TabBar";
import { VoiceBar } from "@/components/VoiceBar";
import { DMLive } from "@/routes/DMLive";
import { DMPrep } from "@/routes/DMPrep";
import { PlayerLive } from "@/routes/PlayerLive";
import { PlayerChar } from "@/routes/PlayerChar";

export function App() {
  const role = useStore((s) => s.role);
  const setRole = useStore((s) => s.setRole);
  const [dmTab, setDmTab] = useState("session");
  const [pTab, setPTab] = useState("session");

  useWebSocket();

  const isLive =
    (role === "dm" && dmTab === "session") ||
    (role === "player" && pTab === "session");

  return (
    <div
      style={{
        background: C.bg,
        color: C.fg,
        minHeight: "100vh",
        fontFamily: C.sans,
      }}
    >
      {/* Top bar */}
      <div
        style={{
          background: C.bgCard,
          borderBottom: `1px solid ${C.border}`,
          padding: "0 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <span
            style={{
              fontFamily: C.mono,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: 2,
              padding: "14px 0",
            }}
          >
            GRIMOIRE
          </span>
          <div style={{ display: "flex", gap: 0 }}>
            {(
              [
                { k: "dm", l: "DM" },
                { k: "player", l: "Player" },
              ] as const
            ).map((r) => (
              <button
                key={r.k}
                onClick={() => setRole(r.k)}
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  fontWeight: role === r.k ? 600 : 400,
                  padding: "14px 16px",
                  background: "none",
                  border: "none",
                  borderBottom:
                    role === r.k
                      ? `2px solid ${C.fg}`
                      : "2px solid transparent",
                  color: role === r.k ? C.fg : C.fgMuted,
                  cursor: "pointer",
                }}
              >
                {r.l}
              </button>
            ))}
          </div>
        </div>
        <div
          style={{
            fontFamily: C.sans,
            fontSize: 13,
            color: C.fgMuted,
          }}
        >
          Lost Mine of Phandelver {"\u2014"} Session 4
        </div>
      </div>

      {/* Sub-tab bar */}
      <div style={{ background: C.bgCard, paddingLeft: 20 }}>
        {role === "dm" ? (
          <TabBar
            tabs={[
              { key: "session", label: "Live Session" },
              { key: "prep", label: "Session Prep" },
            ]}
            active={dmTab}
            onSelect={setDmTab}
          />
        ) : (
          <TabBar
            tabs={[
              { key: "session", label: "Live Session" },
              { key: "character", label: "Character" },
            ]}
            active={pTab}
            onSelect={setPTab}
          />
        )}
      </div>

      {/* Voice bar (live views only) */}
      {isLive && <VoiceBar />}

      {/* View content */}
      {role === "dm" && dmTab === "session" && <DMLive />}
      {role === "dm" && dmTab === "prep" && <DMPrep />}
      {role === "player" && pTab === "session" && <PlayerLive />}
      {role === "player" && pTab === "character" && <PlayerChar />}
    </div>
  );
}

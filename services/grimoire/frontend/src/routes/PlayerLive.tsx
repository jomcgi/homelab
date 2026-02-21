import { C } from "@/lib/tokens";
import { useStore } from "@/lib/store";
import { FeedItem } from "@/components/FeedItem";
import { ChatInput } from "@/components/ChatInput";
import { SBar } from "@/components/SBar";
import { Pill } from "@/components/Pill";
import { HpBar } from "@/components/HpBar";
import {
  MOCK_FEED,
  MOCK_VEX_STATS,
  MOCK_QUICK_ROLLS,
  MOCK_LORE,
} from "@/lib/mock-data";

export function PlayerLive() {
  const players = useStore((s) => s.players);
  const currentPlayerId = useStore((s) => s.currentPlayerId);
  const player = players.find((p) => p.id === currentPlayerId) ?? players[0];

  // Player feed: no table_talk, only private messages for this player
  const feed = MOCK_FEED.filter(
    (i) =>
      i.cls !== "table_talk" &&
      (i.cls !== "private" || i.private_to === currentPlayerId),
  );

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 320px",
        gap: 0,
        height: "calc(100vh - 140px)",
      }}
    >
      {/* Left: Clean narrative feed */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          borderRight: `1px solid ${C.border}`,
          minHeight: 0,
        }}
      >
        <div style={{ flex: 1, overflow: "auto" }}>
          {feed.map((i) => (
            <FeedItem key={i.id} item={i} showCls={false} />
          ))}
        </div>
        <ChatInput />
      </div>

      {/* Right: Character summary + Quick rolls + Lore */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          overflow: "auto",
        }}
      >
        {/* Character summary */}
        <div
          style={{
            padding: "14px 16px",
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: 8,
            }}
          >
            <div>
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 17,
                  fontWeight: 700,
                  color: player.color,
                }}
              >
                {player.name}
              </span>
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fgMuted,
                  marginLeft: 8,
                }}
              >
                {player.class} {player.level}
              </span>
            </div>
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 13,
                color: C.fgMuted,
              }}
            >
              AC {player.ac}
            </span>
          </div>
          <HpBar current={player.hp} max={player.maxHp} />
          {player.conditions.length > 0 && (
            <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
              {player.conditions.map((c) => (
                <Pill key={c} color={C.warn} bg={C.warnBg}>
                  {c}
                </Pill>
              ))}
            </div>
          )}
        </div>

        {/* Ability scores row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(6, 1fr)",
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          {MOCK_VEX_STATS.map((s) => (
            <div
              key={s.name}
              style={{
                padding: "6px 0",
                textAlign: "center",
                borderRight: `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 9,
                  color: C.fgDim,
                  letterSpacing: 1,
                  textTransform: "uppercase",
                }}
              >
                {s.name}
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 15,
                  fontWeight: 700,
                }}
              >
                {s.modifier >= 0 ? "+" : ""}
                {s.modifier}
              </div>
            </div>
          ))}
        </div>

        {/* Quick rolls */}
        <SBar>Quick Rolls</SBar>
        {MOCK_QUICK_ROLLS.map((r) => (
          <button
            key={r.label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              width: "100%",
              padding: "8px 16px",
              fontFamily: C.sans,
              fontSize: 13,
              background: "transparent",
              color: C.fg,
              border: "none",
              borderBottom: `1px solid ${C.border}`,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <div>
              <span style={{ fontWeight: 500 }}>{r.label}</span>
              <span
                style={{
                  fontSize: 11,
                  color: C.fgDim,
                  marginLeft: 6,
                }}
              >
                {r.sub}
              </span>
            </div>
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 12,
                color: C.fgMuted,
              }}
            >
              {r.formula}
            </span>
          </button>
        ))}
        <div style={{ padding: "8px 12px" }}>
          <input
            placeholder="Custom: 2d6+3"
            style={{
              width: "100%",
              fontFamily: C.mono,
              fontSize: 12,
              padding: "7px 10px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>

        {/* Known lore */}
        <SBar>Known Lore</SBar>
        {MOCK_LORE.map((x) => (
          <div
            key={x.fact}
            style={{
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              {x.isNew && (
                <Pill color={C.accent} bg={C.accentLight}>
                  New
                </Pill>
              )}
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fg,
                  lineHeight: 1.5,
                }}
              >
                {x.fact}
              </span>
            </div>
            <div
              style={{
                fontFamily: C.mono,
                fontSize: 10,
                color: C.fgDim,
                marginTop: 3,
              }}
            >
              {x.src}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

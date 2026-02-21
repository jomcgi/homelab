import { useState } from "react";
import { C, CLS } from "@/lib/tokens";
import { useStore } from "@/lib/store";
import { Filters } from "@/components/Filters";
import { FeedItem } from "@/components/FeedItem";
import { ChatInput } from "@/components/ChatInput";
import { SBar } from "@/components/SBar";
import { Pill } from "@/components/Pill";
import { HpBar } from "@/components/HpBar";
import { useReclassify } from "@/lib/api";
import { MOCK_FEED, MOCK_MONSTERS, MOCK_RAG } from "@/lib/mock-data";
import type { Classification, InitiativeEntry } from "@/types";

export function DMLive() {
  const players = useStore((s) => s.players);
  const activeFilters = useStore((s) => s.activeFilters);
  const toggleFilter = useStore((s) => s.toggleFilter);
  const [turn, setTurn] = useState(3);
  const reclassify = useReclassify();

  const feed = MOCK_FEED;

  // Count classifications
  const counts: Partial<Record<Classification, number>> = {};
  feed.forEach((i) => {
    if (i.cls && i.cls !== "private") {
      const cls = i.cls as Classification;
      counts[cls] = (counts[cls] || 0) + 1;
    }
  });

  // Filter feed
  const filtered = feed.filter(
    (i) =>
      i.source === "roll" ||
      i.cls === "private" ||
      !i.cls ||
      activeFilters.includes(i.cls as Classification),
  );

  // Build initiative order
  const all: InitiativeEntry[] = [
    ...players.map((p) => ({ ...p, type: "player" as const })),
    ...MOCK_MONSTERS.map((m) => ({ ...m, type: "monster" as const })),
  ].sort((a, b) => b.init - a.init);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 320px",
        gap: 0,
        height: "calc(100vh - 140px)",
      }}
    >
      {/* Left: Feed */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          borderRight: `1px solid ${C.border}`,
          minHeight: 0,
        }}
      >
        <Filters
          active={activeFilters}
          onToggle={toggleFilter}
          counts={counts}
        />
        <div style={{ flex: 1, overflow: "auto" }}>
          {filtered.map((i) => (
            <FeedItem
              key={i.id}
              item={i}
              isDM
              onReclassify={(eventId, newClass) =>
                reclassify.mutate({ eventId, newClass })
              }
            />
          ))}
        </div>
        <ChatInput isDM />
      </div>

      {/* Right: Initiative + LLM Context */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <SBar right="Round 2">Initiative</SBar>
        {all.map((c, i) => (
          <div
            key={`${c.type}-${c.name}`}
            onClick={() => setTurn(i)}
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
              background: turn === i ? C.accentLight : "transparent",
              borderLeft:
                turn === i ? `3px solid ${C.accent}` : "3px solid transparent",
              cursor: "pointer",
            }}
          >
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 13,
                fontWeight: 700,
                color: C.fgDim,
                minWidth: 22,
              }}
            >
              {c.init}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    fontWeight: 600,
                    color: c.type === "monster" ? C.monster : C.fg,
                  }}
                >
                  {c.name}
                </span>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 12,
                    color: C.fgDim,
                  }}
                >
                  {c.type === "player" ? `${c.class} ${c.level}` : `CR ${c.cr}`}
                </span>
                {c.conditions?.map((d) => (
                  <Pill
                    key={d}
                    color={d === "Poisoned" ? C.err : C.warn}
                    bg={d === "Poisoned" ? C.errBg : C.warnBg}
                  >
                    {d}
                  </Pill>
                ))}
              </div>
              <HpBar current={c.hp} max={c.maxHp} size="small" />
            </div>
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 12,
                color: C.fgDim,
              }}
            >
              AC {c.ac}
            </span>
          </div>
        ))}
        <div
          style={{
            padding: "8px 16px",
            display: "flex",
            gap: 6,
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          <button
            style={{
              flex: 1,
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              padding: 6,
              background: C.fg,
              color: C.bg,
              border: "none",
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            Next Turn
          </button>
          <button
            style={{
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              padding: "6px 12px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            End Round
          </button>
        </div>

        {/* LLM Context Panel */}
        <SBar right="4,102 / 8,192">LLM Context {"\u00B7"} Gemini Flash</SBar>
        {MOCK_RAG.map((c) => (
          <div
            key={`${c.source}-${c.title}`}
            style={{
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
              opacity: c.rel > 0.7 ? 1 : 0.5,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 3,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 11,
                    color: C.accent,
                    fontWeight: 600,
                  }}
                >
                  {c.source}
                </span>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 13,
                    fontWeight: 600,
                  }}
                >
                  {c.title}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 4,
                  alignItems: "center",
                }}
              >
                {c.auto && (
                  <Pill color={CLS.rules.color} bg={CLS.rules.bg}>
                    Auto
                  </Pill>
                )}
                {c.pinned && (
                  <Pill color={C.accent} bg={C.accentLight}>
                    {"\uD83D\uDCCC"}
                  </Pill>
                )}
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 10,
                    color: C.fgDim,
                  }}
                >
                  {(c.rel * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div
              style={{
                fontFamily: C.sans,
                fontSize: 12,
                color: C.fgMuted,
                lineHeight: 1.5,
              }}
            >
              {c.text}
            </div>
          </div>
        ))}
        <div style={{ padding: "8px 12px" }}>
          <input
            placeholder="Ask a rule question..."
            style={{
              width: "100%",
              fontFamily: C.sans,
              fontSize: 13,
              padding: "8px 12px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>
      </div>
    </div>
  );
}

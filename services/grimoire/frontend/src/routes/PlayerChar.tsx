import { C } from "@/lib/tokens";
import { useStore } from "@/lib/store";
import { Card } from "@/components/Card";
import { SBar } from "@/components/SBar";
import { Pill } from "@/components/Pill";
import {
  MOCK_VEX_FULL_STATS,
  MOCK_INVENTORY,
  MOCK_JOURNAL,
  MOCK_FULL_LORE,
} from "@/lib/mock-data";

export function PlayerChar() {
  const players = useStore((s) => s.players);
  const currentPlayerId = useStore((s) => s.currentPlayerId);
  const player = players.find((p) => p.id === currentPlayerId) ?? players[0];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 20,
        padding: 20,
      }}
    >
      {/* Left column: Character sheet + Inventory */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <Card>
          <div style={{ padding: 20 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: 16,
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 22,
                    fontWeight: 700,
                    color: player.color,
                  }}
                >
                  {player.name}
                </span>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 15,
                    color: C.fgMuted,
                    marginLeft: 10,
                  }}
                >
                  {player.class} {player.level}
                </span>
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 14,
                  color: C.fgMuted,
                }}
              >
                AC {player.ac} {"\u00B7"} HP {player.maxHp}
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: 8,
              }}
            >
              {MOCK_VEX_FULL_STATS.map((s) => (
                <div
                  key={s.name}
                  style={{
                    border: `1px solid ${C.border}`,
                    borderRadius: 3,
                    padding: 12,
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontFamily: C.sans,
                      fontSize: 11,
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
                      fontSize: 24,
                      fontWeight: 700,
                    }}
                  >
                    {s.modifier >= 0 ? "+" : ""}
                    {s.modifier}
                  </div>
                  <div
                    style={{
                      fontFamily: C.mono,
                      fontSize: 13,
                      color: C.fgDim,
                    }}
                  >
                    {s.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
        <Card>
          <SBar>Inventory</SBar>
          {MOCK_INVENTORY.map((x) => (
            <div
              key={x.name}
              style={{
                padding: "10px 20px",
                borderBottom: `1px solid ${C.border}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    fontWeight: 500,
                  }}
                >
                  {x.name}
                </span>
                <div
                  style={{
                    fontFamily: C.sans,
                    fontSize: 12,
                    color: C.fgDim,
                    marginTop: 2,
                  }}
                >
                  {x.detail}
                </div>
              </div>
              {x.equipped && (
                <Pill color={C.ok} bg={C.okBg}>
                  Equipped
                </Pill>
              )}
            </div>
          ))}
          <div
            style={{
              padding: "10px 20px",
              fontFamily: C.mono,
              fontSize: 14,
              color: C.warn,
              fontWeight: 600,
            }}
          >
            47 gp {"\u00B7"} 12 sp {"\u00B7"} 3 cp
          </div>
        </Card>
      </div>

      {/* Right column: Journal + Known Lore */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <Card>
          <SBar>Journal</SBar>
          {MOCK_JOURNAL.map((s) => (
            <div
              key={s.n}
              style={{
                padding: "14px 20px",
                borderBottom: `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "baseline",
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    fontWeight: 600,
                  }}
                >
                  Session {s.n}
                </span>
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 12,
                    color: C.fgDim,
                  }}
                >
                  {s.date}
                </span>
              </div>
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 14,
                  color: C.fg,
                  lineHeight: 1.6,
                }}
              >
                {s.text}
              </div>
            </div>
          ))}
        </Card>
        <Card>
          <SBar>Known Lore</SBar>
          {MOCK_FULL_LORE.map((x) => (
            <div
              key={x.fact}
              style={{
                padding: "10px 20px",
                borderBottom: `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 14,
                  color: C.fg,
                  lineHeight: 1.5,
                }}
              >
                {x.fact}
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 11,
                  color: C.fgDim,
                  marginTop: 4,
                }}
              >
                Source: {x.src}
              </div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

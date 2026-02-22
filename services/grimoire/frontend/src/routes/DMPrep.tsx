import { useState } from "react";
import { C } from "@/lib/tokens";
import { useStore } from "@/lib/store";
import { useRAGQuery } from "@/lib/api";
import { Card } from "@/components/Card";
import { SBar } from "@/components/SBar";
import { Pill } from "@/components/Pill";
import {
  MOCK_ENCOUNTERS,
  MOCK_SESSIONS,
  MOCK_WORLD_STATE,
} from "@/lib/mock-data";

export function DMPrep() {
  const players = useStore((s) => s.players);
  const [ruleQuery, setRuleQuery] = useState("");
  const rag = useRAGQuery();

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 20,
        padding: 20,
      }}
    >
      {/* Left column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <Card>
          <SBar right="Session 4">Planned Encounters</SBar>
          {MOCK_ENCOUNTERS.map((e) => (
            <div
              key={e.name}
              style={{
                padding: "14px 20px",
                borderBottom: `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 15,
                    fontWeight: 600,
                  }}
                >
                  {e.name}
                </span>
                <Pill
                  color={
                    e.diff === "Deadly"
                      ? C.err
                      : e.diff === "Hard"
                        ? C.warn
                        : C.fgMuted
                  }
                  bg={
                    e.diff === "Deadly"
                      ? C.errBg
                      : e.diff === "Hard"
                        ? C.warnBg
                        : C.bgMuted
                  }
                >
                  {e.diff}
                </Pill>
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 13,
                  color: C.fgMuted,
                  marginBottom: 4,
                }}
              >
                {e.monsters}
              </div>
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fgMuted,
                  lineHeight: 1.5,
                }}
              >
                {e.notes}
              </div>
            </div>
          ))}
          <div style={{ padding: "12px 20px" }}>
            <button
              style={{
                fontFamily: C.sans,
                fontSize: 13,
                fontWeight: 500,
                padding: "8px 16px",
                background: C.bgMuted,
                color: C.fg,
                border: `1px solid ${C.border}`,
                borderRadius: 3,
                cursor: "pointer",
                width: "100%",
              }}
            >
              + Generate Encounter from Sourcebook
            </button>
          </div>
        </Card>
        <Card>
          <SBar>Party</SBar>
          {players.map((p) => (
            <div
              key={p.id}
              style={{
                padding: "10px 20px",
                borderBottom: `1px solid ${C.border}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    fontWeight: 600,
                    color: p.color,
                  }}
                >
                  {p.name}
                </span>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 13,
                    color: C.fgMuted,
                    marginLeft: 8,
                  }}
                >
                  {p.class} {p.level}
                </span>
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 13,
                  color: C.fgMuted,
                }}
              >
                AC {p.ac} {"\u00B7"} HP {p.maxHp}
              </div>
            </div>
          ))}
        </Card>
      </div>

      {/* Right column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <Card>
          <SBar>Session History</SBar>
          {MOCK_SESSIONS.map((s) => (
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
                  color: C.fgMuted,
                  lineHeight: 1.55,
                }}
              >
                {s.text}
              </div>
            </div>
          ))}
        </Card>
        <Card>
          <SBar>World State</SBar>
          {MOCK_WORLD_STATE.map((x) => (
            <div
              key={x.key}
              style={{
                padding: "10px 20px",
                borderBottom: `1px solid ${C.border}`,
                display: "flex",
                gap: 12,
              }}
            >
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  fontWeight: 600,
                  color: C.fgMuted,
                  minWidth: 100,
                  flexShrink: 0,
                }}
              >
                {x.key}
              </span>
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 14,
                  color: C.fg,
                  lineHeight: 1.5,
                }}
              >
                {x.value}
              </span>
            </div>
          ))}
        </Card>
        <Card>
          <SBar>Rule Lookup</SBar>
          <div style={{ padding: "12px 20px" }}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const trimmed = ruleQuery.trim();
                if (trimmed) rag.mutate({ query: trimmed });
              }}
            >
              <input
                value={ruleQuery}
                onChange={(e) => setRuleQuery(e.target.value)}
                placeholder="Search rules, monsters, spells, items..."
                style={{
                  width: "100%",
                  fontFamily: C.sans,
                  fontSize: 14,
                  padding: "10px 14px",
                  background: C.bgMuted,
                  color: C.fg,
                  border: `1px solid ${C.border}`,
                  borderRadius: 3,
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </form>
            {rag.isPending && (
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fgDim,
                  marginTop: 12,
                }}
              >
                Searching...
              </div>
            )}
            {rag.isError && (
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.err,
                  marginTop: 12,
                }}
              >
                {rag.error instanceof Error
                  ? rag.error.message
                  : "Search failed"}
              </div>
            )}
            {rag.data && (
              <div style={{ marginTop: 12 }}>
                <div
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    color: C.fg,
                    lineHeight: 1.6,
                    marginBottom: 10,
                  }}
                >
                  {rag.data.answer}
                </div>
                {rag.data.citations.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      marginBottom: 10,
                    }}
                  >
                    {rag.data.citations.map((c, i) => (
                      <Pill key={i} color={C.accent} bg={C.accentLight}>
                        {c.source_book} p.{c.page} — {c.section}
                      </Pill>
                    ))}
                  </div>
                )}
                {rag.data.campaign_context &&
                  rag.data.campaign_context.length > 0 && (
                    <div
                      style={{
                        borderTop: `1px solid ${C.border}`,
                        paddingTop: 8,
                        marginTop: 4,
                      }}
                    >
                      <div
                        style={{
                          fontFamily: C.sans,
                          fontSize: 11,
                          fontWeight: 600,
                          color: C.fgDim,
                          textTransform: "uppercase",
                          letterSpacing: 0.5,
                          marginBottom: 6,
                        }}
                      >
                        Campaign Context
                      </div>
                      {rag.data.campaign_context.map((ctx, i) => (
                        <div
                          key={i}
                          style={{
                            fontFamily: C.sans,
                            fontSize: 13,
                            color: C.fgMuted,
                            lineHeight: 1.5,
                            marginBottom: 4,
                          }}
                        >
                          <span
                            style={{
                              fontFamily: C.mono,
                              fontSize: 11,
                              color: C.fgDim,
                              marginRight: 6,
                            }}
                          >
                            [{ctx.type}]
                          </span>
                          <span style={{ fontWeight: 600 }}>{ctx.name}</span>
                          {" — "}
                          {ctx.summary}
                        </div>
                      ))}
                    </div>
                  )}
              </div>
            )}
            <div
              style={{
                fontFamily: C.sans,
                fontSize: 12,
                color: C.fgDim,
                marginTop: 8,
              }}
            >
              Searches Firestore vectors across all ingested sourcebooks. Gemini
              Flash generates answers with page citations.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

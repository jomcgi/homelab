import { C, mono } from "../tokens.js";

export function SubagentProgress({ subagents }) {
  const entries = Object.entries(subagents || {});
  if (entries.length === 0) return null;

  return (
    <div style={{ margin: "8px 0" }}>
      {entries.map(([id, agent]) => (
        <div
          key={id}
          style={{
            padding: "6px 0 6px 12px",
            borderLeft: `2px solid ${C.accentBlue}`,
            marginBottom: 6,
            borderRadius: 2,
          }}
        >
          {/* Header */}
          <div
            style={{
              fontFamily: mono,
              fontSize: 12,
              fontWeight: 600,
              color: C.textSec,
              marginBottom: 4,
            }}
          >
            <span style={{ color: C.accentBlue }}>&#x23FA; </span>
            {agent.name || agent.type || "agent"}
            {!agent.name && agent.desc && (
              <span style={{ fontWeight: 400, color: C.textTer }}>
                {" "}({agent.desc.length > 40 ? agent.desc.slice(0, 37) + "..." : agent.desc})
              </span>
            )}
          </div>

          {/* Tool steps */}
          {agent.steps.length > 0 && (
            <div style={{ paddingLeft: 12 }}>
              {agent.steps.map((step, si) => (
                <div
                  key={si}
                  style={{
                    fontFamily: mono,
                    fontSize: 11,
                    color: C.textTer,
                    padding: "1px 0",
                    display: "flex",
                    alignItems: "baseline",
                    gap: 6,
                  }}
                >
                  <span style={{ color: C.border }}>&#x251C;</span>
                  <span>{step}</span>
                </div>
              ))}
            </div>
          )}

          {/* Overflow count */}
          {agent.toolCount > 3 && (
            <div
              style={{
                fontFamily: mono,
                fontSize: 11,
                color: C.textFaint,
                paddingLeft: 12,
                marginTop: 2,
              }}
            >
              +{agent.toolCount - 3} more tool uses
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

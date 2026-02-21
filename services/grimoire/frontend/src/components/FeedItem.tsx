import { C, CLS } from "@/lib/tokens";
import { Pill } from "./Pill";
import { useStore } from "@/lib/store";
import type { FeedEvent, Classification } from "@/types";

interface FeedItemProps {
  item: FeedEvent;
  showCls?: boolean;
  isDM?: boolean;
  onReclassify?: (eventId: string, newClass: Classification) => void;
}

export function FeedItem({
  item,
  showCls = true,
  isDM = false,
  onReclassify,
}: FeedItemProps) {
  const players = useStore((s) => s.players);
  const p = players.find((pl) => pl.name === item.who);
  const nc =
    item.who === "DM" || item.who?.startsWith("DM") ? C.warn : p?.color || C.fg;
  const c =
    item.cls && item.cls !== "private" ? CLS[item.cls as Classification] : null;

  // Roll item
  if (item.source === "roll" && item.roll) {
    return (
      <div
        style={{
          padding: "6px 20px",
          borderBottom: `1px solid ${C.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: C.bgMuted,
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "baseline",
          }}
        >
          <span style={{ fontFamily: C.mono, fontSize: 11, color: C.fgDim }}>
            {item.time}
          </span>
          <span
            style={{
              fontFamily: C.sans,
              fontSize: 13,
              fontWeight: 600,
              color: nc,
            }}
          >
            {item.who}
          </span>
          <span style={{ fontFamily: C.sans, fontSize: 13, color: C.fgMuted }}>
            {item.roll.type}
          </span>
          <span style={{ fontFamily: C.mono, fontSize: 12, color: C.fgDim }}>
            {item.roll.formula}
          </span>
        </div>
        <span
          style={{
            fontFamily: C.mono,
            fontSize: 16,
            fontWeight: 700,
            color: item.roll.result >= 20 ? C.ok : C.fg,
          }}
        >
          {item.roll.result}
        </span>
      </div>
    );
  }

  // Private message
  if (item.cls === "private") {
    return (
      <div
        style={{
          margin: "8px 12px",
          padding: "12px 16px",
          borderRadius: 4,
          background: C.privateBg,
          border: `1px solid ${C.private}40`,
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            marginBottom: 6,
          }}
        >
          <Pill color={C.private} bg={`${C.private}18`}>
            Private to {item.private_to}
          </Pill>
          <span
            style={{
              fontFamily: C.sans,
              fontSize: 13,
              fontWeight: 600,
              color: C.private,
            }}
          >
            {item.who}
          </span>
          <span style={{ fontFamily: C.mono, fontSize: 11, color: C.fgDim }}>
            {item.time}
          </span>
        </div>
        <div
          style={{
            fontFamily: C.sans,
            fontSize: 14,
            color: C.fg,
            lineHeight: 1.55,
          }}
        >
          {item.text}
        </div>
      </div>
    );
  }

  // Standard feed item
  return (
    <div
      style={{
        padding: "10px 20px",
        borderBottom: `1px solid ${C.border}`,
        background: item.rag ? C.rulesBg : "transparent",
        borderLeft: item.rag ? `3px solid ${C.rules}` : "3px solid transparent",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          marginBottom: 4,
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontFamily: C.sans,
            fontSize: 13,
            fontWeight: 600,
            color: nc,
          }}
        >
          {item.who}
        </span>
        <span style={{ fontFamily: C.mono, fontSize: 11, color: C.fgDim }}>
          {item.time}
        </span>
        {item.source === "voice" && (
          <span
            style={{
              fontFamily: C.mono,
              fontSize: 10,
              color: C.gcp,
              opacity: 0.6,
            }}
          >
            {"\uD83C\uDF99"}
          </span>
        )}
        {showCls && c && (
          <Pill color={c.color} bg={c.bg}>
            {c.icon} {c.label}
          </Pill>
        )}
        {isDM && item.conf != null && item.conf < 0.85 && (
          <Pill color={C.warn} bg={C.warnBg}>
            Low conf. {(item.conf * 100).toFixed(0)}%
          </Pill>
        )}
        {item.rag && (
          <Pill color={C.rules} bg={`${C.rules}15`}>
            {"\u21B3"} RAG triggered
          </Pill>
        )}
      </div>
      <div
        style={{
          fontFamily: C.sans,
          fontSize: 14,
          color: C.fg,
          lineHeight: 1.55,
        }}
      >
        {item.text}
      </div>
      {isDM && c && (
        <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
          {(
            Object.entries(CLS) as [
              Classification,
              (typeof CLS)[Classification],
            ][]
          )
            .filter(([k]) => k !== item.cls && k !== "table_talk")
            .map(([key, cl]) => (
              <button
                key={key}
                onClick={() => onReclassify?.(item.id, key)}
                style={{
                  fontFamily: C.sans,
                  fontSize: 10,
                  padding: "1px 6px",
                  borderRadius: 2,
                  background: "transparent",
                  border: `1px solid ${C.border}`,
                  color: C.fgDim,
                  cursor: "pointer",
                  opacity: 0.4,
                }}
                title={`Reclassify as ${cl.label}`}
              >
                {cl.icon}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

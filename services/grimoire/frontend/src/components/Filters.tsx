import { C, CLS } from "@/lib/tokens";
import type { Classification } from "@/types";

interface FiltersProps {
  active: Classification[];
  onToggle: (key: Classification) => void;
  counts: Partial<Record<Classification, number>>;
}

export function Filters({ active, onToggle, counts }: FiltersProps) {
  return (
    <div
      style={{
        padding: "8px 20px",
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        gap: 6,
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          fontFamily: C.sans,
          fontSize: 11,
          color: C.fgDim,
          marginRight: 4,
          textTransform: "uppercase",
          letterSpacing: 1,
        }}
      >
        Filter
      </span>
      {(
        Object.entries(CLS) as [Classification, (typeof CLS)[Classification]][]
      ).map(([key, c]) => {
        const on = active.includes(key);
        return (
          <button
            key={key}
            onClick={() => onToggle(key)}
            style={{
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              padding: "4px 10px",
              borderRadius: 3,
              cursor: "pointer",
              border: on ? `1.5px solid ${c.color}` : `1px solid ${C.border}`,
              background: on ? c.bg : "transparent",
              color: on ? c.color : C.fgDim,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <span style={{ fontSize: 11 }}>{c.icon}</span>
            {c.label}
            {(counts[key] || 0) > 0 && (
              <span
                style={{
                  fontFamily: C.mono,
                  fontSize: 10,
                  opacity: 0.7,
                }}
              >
                {counts[key]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

import { C } from "@/lib/tokens";

interface HpBarProps {
  current: number;
  max: number;
  size?: "normal" | "small";
}

export function HpBar({ current, max, size = "normal" }: HpBarProps) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  const color = pct > 50 ? C.ok : pct > 25 ? C.warn : C.err;
  const h = size === "small" ? 4 : 6;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: h,
          background: C.bgMuted,
          borderRadius: h / 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: h / 2,
            transition: "width 0.3s",
          }}
        />
      </div>
      <span
        style={{
          fontFamily: C.mono,
          fontSize: size === "small" ? 12 : 13,
          color,
          fontWeight: 600,
          minWidth: 48,
          textAlign: "right",
        }}
      >
        {current}/{max}
      </span>
    </div>
  );
}

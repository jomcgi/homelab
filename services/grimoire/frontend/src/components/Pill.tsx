import { C } from "@/lib/tokens";

interface PillProps {
  children: React.ReactNode;
  color?: string;
  bg?: string;
}

export function Pill({
  children,
  color = C.fgMuted,
  bg = C.bgMuted,
}: PillProps) {
  return (
    <span
      style={{
        fontFamily: C.sans,
        fontSize: 11,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 3,
        background: bg,
        color,
        letterSpacing: 0.3,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

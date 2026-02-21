import { C } from "@/lib/tokens";

interface SBarProps {
  children: React.ReactNode;
  right?: React.ReactNode;
  muted?: boolean;
}

export function SBar({ children, right, muted }: SBarProps) {
  return (
    <div
      style={{
        padding: "10px 20px",
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        background: muted ? C.bgMuted : C.bgCard,
        flexShrink: 0,
      }}
    >
      <span
        style={{
          fontFamily: C.sans,
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: 1.2,
          color: C.fgMuted,
        }}
      >
        {children}
      </span>
      {right && (
        <span style={{ fontFamily: C.mono, fontSize: 12, color: C.fgDim }}>
          {right}
        </span>
      )}
    </div>
  );
}

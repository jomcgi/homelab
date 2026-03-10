import { C } from "@/lib/tokens";

interface CardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export function Card({ children, style: s = {} }: CardProps) {
  return (
    <div
      style={{
        background: C.bgCard,
        border: `1px solid ${C.border}`,
        borderRadius: 4,
        overflow: "hidden",
        ...s,
      }}
    >
      {children}
    </div>
  );
}

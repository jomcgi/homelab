import { C } from "@/lib/tokens";

interface Tab {
  key: string;
  label: string;
}

interface TabBarProps {
  tabs: Tab[];
  active: string;
  onSelect: (key: string) => void;
}

export function TabBar({ tabs, active, onSelect }: TabBarProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: 0,
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onSelect(t.key)}
          style={{
            fontFamily: C.sans,
            fontSize: 13,
            fontWeight: active === t.key ? 600 : 400,
            padding: "10px 20px",
            background: "none",
            border: "none",
            borderBottom:
              active === t.key ? `2px solid ${C.fg}` : "2px solid transparent",
            color: active === t.key ? C.fg : C.fgMuted,
            cursor: "pointer",
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

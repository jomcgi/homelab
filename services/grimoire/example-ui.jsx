import { useState } from "react";

// --- Tokens ---
const C = {
  bg: "#fafaf8",
  bgCard: "#fff",
  bgHover: "#f5f5f3",
  bgMuted: "#f0efed",
  fg: "#1a1a1a",
  fgMuted: "#666",
  fgDim: "#999",
  border: "#e5e4e2",
  accent: "#2563eb",
  accentLight: "#eff4ff",
  ok: "#16a34a",
  okBg: "#f0fdf4",
  warn: "#d97706",
  warnBg: "#fffbeb",
  err: "#dc2626",
  errBg: "#fef2f2",
  private: "#9333ea",
  privateBg: "#faf5ff",
  monster: "#dc2626",
  icAction: "#2563eb",
  icActionBg: "#eff4ff",
  icDialogue: "#7c3aed",
  icDialogueBg: "#f5f3ff",
  rules: "#d97706",
  rulesBg: "#fffbeb",
  dmNarrate: "#059669",
  dmNarrateBg: "#ecfdf5",
  dmRuling: "#0891b2",
  dmRulingBg: "#ecfeff",
  tableTalk: "#9ca3af",
  tableTalkBg: "#f9fafb",
  gcp: "#4285f4",
  gcpBg: "#e8f0fe",
  sans: "'Inter', system-ui, -apple-system, sans-serif",
  mono: "ui-monospace, 'SF Mono', 'Cascadia Mono', 'Courier New', monospace",
};

const CLS = {
  ic_action: {
    label: "Action",
    color: C.icAction,
    bg: C.icActionBg,
    icon: "⚔",
  },
  ic_dialogue: {
    label: "Dialogue",
    color: C.icDialogue,
    bg: C.icDialogueBg,
    icon: "💬",
  },
  rules: { label: "Rules", color: C.rules, bg: C.rulesBg, icon: "📖" },
  dm_narration: {
    label: "Narration",
    color: C.dmNarrate,
    bg: C.dmNarrateBg,
    icon: "🎭",
  },
  dm_ruling: {
    label: "Ruling",
    color: C.dmRuling,
    bg: C.dmRulingBg,
    icon: "⚖",
  },
  table_talk: {
    label: "Table",
    color: C.tableTalk,
    bg: C.tableTalkBg,
    icon: "☕",
  },
};

const PLAYERS = [
  {
    id: "kael",
    name: "Kael",
    class: "Fighter",
    level: 5,
    hp: 45,
    maxHp: 52,
    ac: 18,
    init: 17,
    conditions: ["Blessed"],
    color: "#dc2626",
  },
  {
    id: "lyra",
    name: "Lyra",
    class: "Wizard",
    level: 5,
    hp: 28,
    maxHp: 28,
    ac: 13,
    init: 15,
    conditions: [],
    color: "#2563eb",
  },
  {
    id: "theron",
    name: "Theron",
    class: "Cleric",
    level: 5,
    hp: 38,
    maxHp: 41,
    ac: 16,
    init: 12,
    conditions: [],
    color: "#16a34a",
  },
  {
    id: "vex",
    name: "Vex",
    class: "Rogue",
    level: 5,
    hp: 19,
    maxHp: 33,
    ac: 15,
    init: 22,
    conditions: ["Poisoned"],
    color: "#d97706",
  },
];
const MONSTERS = [
  {
    name: "Owlbear",
    hp: 42,
    maxHp: 59,
    ac: 13,
    init: 8,
    cr: "3",
    conditions: [],
  },
  {
    name: "Goblin Boss",
    hp: 11,
    maxHp: 21,
    ac: 17,
    init: 14,
    cr: "1",
    conditions: ["Prone"],
  },
  {
    name: "Goblin ×3",
    hp: 7,
    maxHp: 7,
    ac: 15,
    init: 6,
    cr: "¼",
    conditions: [],
  },
];

const FEED = [
  {
    id: 1,
    who: "DM",
    time: "19:42",
    source: "voice",
    cls: "dm_narration",
    text: "As you push through the undergrowth, the forest goes quiet. Too quiet. The birds have stopped. You can smell something musky — like wet feathers and blood.",
    conf: 0.96,
  },
  {
    id: 2,
    who: "Vex",
    time: "19:42",
    source: "voice",
    cls: "ic_action",
    text: "I stop and hold up a fist. Everybody freeze. I want to look around — Perception check.",
    conf: 0.94,
  },
  {
    id: 3,
    who: "Vex",
    time: "19:42",
    source: "roll",
    roll: { formula: "1d20+3", result: 18, type: "Perception" },
  },
  {
    id: 4,
    who: "DM",
    time: "19:42",
    source: "voice",
    cls: "dm_narration",
    text: "You spot movement in the canopy — a massive shape on a thick branch. Below, three small figures behind a fallen log. Goblins. And that shape... that's an owlbear.",
    conf: 0.97,
  },
  {
    id: 5,
    who: "Lyra",
    time: "19:43",
    source: "voice",
    cls: "rules",
    text: "Wait — can I cast Bless before combat? If Vex spotted them, are we surprised or do we get a round?",
    conf: 0.91,
    rag: true,
  },
  {
    id: 6,
    who: "DM",
    time: "19:43",
    source: "voice",
    cls: "dm_ruling",
    text: "Good question. Vex spotted them, so the party is not surprised. But we're rolling initiative — Lyra, you can Bless on your first turn if you beat them.",
    conf: 0.93,
  },
  {
    id: 7,
    who: "Kael",
    time: "19:43",
    source: "voice",
    cls: "table_talk",
    text: "Oh man, an owlbear? Those things hit like trucks.",
    conf: 0.88,
  },
  {
    id: 8,
    who: "Theron",
    time: "19:43",
    source: "voice",
    cls: "table_talk",
    text: "I've got healing word prepped, we'll be fine.",
    conf: 0.72,
  },
  {
    id: 9,
    who: "DM",
    time: "19:43",
    source: "voice",
    cls: "dm_narration",
    text: "Everyone roll initiative.",
    conf: 0.95,
  },
  {
    id: 10,
    who: "Vex",
    time: "19:43",
    source: "roll",
    roll: { formula: "1d20+4", result: 22, type: "Initiative" },
  },
  {
    id: 11,
    who: "Kael",
    time: "19:43",
    source: "roll",
    roll: { formula: "1d20+1", result: 17, type: "Initiative" },
  },
  {
    id: 12,
    who: "Vex",
    time: "19:44",
    source: "voice",
    cls: "ic_dialogue",
    text: "Alright — Kael, take the big one. Theron, keep us standing. Lyra, light them up. I'll handle the boss.",
    conf: 0.95,
  },
  {
    id: 13,
    who: "Vex",
    time: "19:44",
    source: "voice",
    cls: "ic_action",
    text: "I drop from my branch and drive my shortsword into the goblin boss.",
    conf: 0.97,
  },
  {
    id: 14,
    who: "Vex",
    time: "19:44",
    source: "roll",
    roll: { formula: "1d20+7", result: 24, type: "Attack → Goblin Boss" },
  },
  {
    id: 15,
    who: "Vex",
    time: "19:44",
    source: "roll",
    roll: { formula: "1d6+4+3d6", result: 19, type: "Sneak Attack Damage" },
  },
  {
    id: 16,
    who: "DM",
    time: "19:44",
    source: "voice",
    cls: "dm_narration",
    text: "Nineteen damage. The goblin boss staggers, blood pouring from his chest. He snarls something in Goblin.",
    conf: 0.98,
  },
  {
    id: 17,
    who: "DM",
    time: "19:44",
    source: "typed",
    cls: "private",
    text: "You understand Goblin — he's calling for reinforcements from the cave. Maybe two rounds.",
    private_to: "vex",
  },
  {
    id: 18,
    who: "Kael",
    time: "19:45",
    source: "voice",
    cls: "ic_action",
    text: "My turn. I charge the owlbear — two attacks with my longsword.",
    conf: 0.96,
  },
  {
    id: 19,
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: { formula: "1d20+7", result: 14, type: "Attack → Owlbear" },
  },
  {
    id: 20,
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: { formula: "1d20+7", result: 21, type: "Attack → Owlbear (2nd)" },
  },
  {
    id: 21,
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: { formula: "1d8+4", result: 11, type: "Longsword Damage" },
  },
  {
    id: 22,
    who: "DM",
    time: "19:45",
    source: "voice",
    cls: "dm_narration",
    text: "First swing goes wide. The second catches it across the flank — eleven damage. It screams, a horrible shrieking sound.",
    conf: 0.97,
  },
  {
    id: 23,
    who: "Lyra",
    time: "19:46",
    source: "voice",
    cls: "rules",
    text: "Does that shriek force a concentration check? I'm holding Bless.",
    conf: 0.89,
    rag: true,
  },
];

const RAG = [
  {
    source: "PHB p.203",
    title: "Concentration",
    text: "Taking damage → Con save. DC = 10 or half damage, whichever is higher. Owlbear shriek is flavor, not damage — no save needed.",
    rel: 0.95,
    auto: true,
  },
  {
    source: "MM p.249",
    title: "Owlbear",
    text: "Multiattack: beak + claws. Keen Sight/Smell: adv on Perception. No shriek ability in stat block.",
    rel: 0.94,
    pinned: true,
  },
  {
    source: "MM p.166",
    title: "Goblin Boss — Redirect Attack",
    text: "Reaction: swap with goblin within 5ft when targeted. Chosen goblin becomes target.",
    rel: 0.91,
  },
  {
    source: "PHB p.96",
    title: "Sneak Attack (5th)",
    text: "3d6 extra, once/turn. Advantage or ally within 5ft. Finesse or ranged weapon.",
    rel: 0.87,
  },
];

const PREP_ENC = [
  {
    name: "Cragmaw Cave — Entry",
    monsters: "4× Goblin, 2× Wolf",
    diff: "Medium",
    notes: "Stealth DC 12 to avoid lookout. Wolves chained.",
  },
  {
    name: "Cragmaw Cave — Bridge",
    monsters: "1× Goblin Boss, 3× Goblin",
    diff: "Hard",
    notes: "Boss can trigger flood. Dex DC 13 or swept away.",
  },
  {
    name: "Cragmaw Cave — Klarg",
    monsters: "1× Bugbear, 1× Wolf, 2× Goblin",
    diff: "Deadly",
    notes: "Klarg negotiates below half HP. Has stolen goods.",
  },
];

const SESSIONS = [
  {
    n: 3,
    date: "Feb 9",
    text: "Ambushed on Triboar Trail. Captured goblin → Cragmaw hideout. Gundren taken to 'the castle.'",
  },
  {
    n: 2,
    date: "Feb 2",
    text: "Arrived Phandalin. Met Sildar Hallwinter. Investigated Redbrand thugs at Stonehill Inn.",
  },
];

// ---- Shared Components ----
const SBar = ({ children, right, muted }) => (
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
const Pill = ({ children, color = C.fgMuted, bg = C.bgMuted }) => (
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
const HpBar = ({ current, max, size = "normal" }) => {
  const pct = Math.max(0, (current / max) * 100);
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
};
const Card = ({ children, style: s = {} }) => (
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
const TabBar = ({ tabs, active, onSelect }) => (
  <div
    style={{ display: "flex", gap: 0, borderBottom: `1px solid ${C.border}` }}
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

// ---- Voice Bar ----
const VoiceBar = () => {
  const speaking = [PLAYERS[3]];
  return (
    <div
      style={{
        padding: "6px 20px",
        background: C.gcpBg,
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: C.ok, fontSize: 8 }}>●</span>
          <span
            style={{
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              color: C.fgMuted,
            }}
          >
            Voice Connected
          </span>
        </div>
        <span style={{ color: C.border }}>|</span>
        <div style={{ display: "flex", gap: 8 }}>
          {PLAYERS.map((p) => {
            const isSpeaking = speaking.find((s) => s.id === p.id);
            return (
              <div
                key={p.id}
                style={{ display: "flex", alignItems: "center", gap: 4 }}
              >
                <div
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: isSpeaking ? p.color : C.bgMuted,
                    border: `1.5px solid ${p.color}`,
                    boxShadow: isSpeaking ? `0 0 6px ${p.color}50` : "none",
                  }}
                />
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 12,
                    color: isSpeaking ? p.color : C.fgDim,
                    fontWeight: isSpeaking ? 600 : 400,
                  }}
                >
                  {p.name}
                </span>
              </div>
            );
          })}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: C.bgMuted,
                border: `1.5px solid ${C.warn}`,
              }}
            />
            <span style={{ fontFamily: C.sans, fontSize: 12, color: C.fgDim }}>
              DM
            </span>
          </div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Pill color={C.gcp} bg={`${C.gcp}15`}>
          Gemini Live
        </Pill>
        <Pill color={C.fgDim} bg={C.bgMuted}>
          Firestore RAG
        </Pill>
        <span style={{ fontFamily: C.mono, fontSize: 11, color: C.fgDim }}>
          ~280ms
        </span>
      </div>
    </div>
  );
};

// ---- Classification Filters ----
const Filters = ({ active, onToggle, counts }) => (
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
    {Object.entries(CLS).map(([key, c]) => {
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
            <span style={{ fontFamily: C.mono, fontSize: 10, opacity: 0.7 }}>
              {counts[key]}
            </span>
          )}
        </button>
      );
    })}
  </div>
);

// ---- Feed Item ----
const FeedItem = ({ item, showCls = true, isDM = false }) => {
  const p = PLAYERS.find((p) => p.name === item.who);
  const nc =
    item.who === "DM" || item.who?.startsWith("DM") ? C.warn : p?.color || C.fg;
  const c = item.cls ? CLS[item.cls] : null;

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
        <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
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
            🎙
          </span>
        )}
        {showCls && c && (
          <Pill color={c.color} bg={c.bg}>
            {c.icon} {c.label}
          </Pill>
        )}
        {isDM && item.conf && item.conf < 0.85 && (
          <Pill color={C.warn} bg={C.warnBg}>
            Low conf. {(item.conf * 100).toFixed(0)}%
          </Pill>
        )}
        {item.rag && (
          <Pill color={C.rules} bg={`${C.rules}15`}>
            ↳ RAG triggered
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
          {Object.entries(CLS)
            .filter(([k]) => k !== item.cls && k !== "table_talk")
            .map(([key, cl]) => (
              <button
                key={key}
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
};

// ---- Chat Input ----
const ChatInput = ({ isDM = false }) => {
  const [input, setInput] = useState("");
  const [ch, setCh] = useState("public");
  return (
    <div style={{ borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
      {ch === "private" && (
        <div
          style={{
            padding: "6px 20px",
            background: C.privateBg,
            fontFamily: C.sans,
            fontSize: 12,
            color: C.private,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          Whispering to: <strong>Vex</strong>
          <button
            onClick={() => setCh("public")}
            style={{
              marginLeft: "auto",
              fontFamily: C.sans,
              fontSize: 11,
              background: "none",
              border: "none",
              color: C.private,
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Cancel
          </button>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center" }}>
        <select
          value={ch}
          onChange={(e) => setCh(e.target.value)}
          style={{
            fontFamily: C.sans,
            fontSize: 12,
            padding: "10px 12px",
            background: C.bgMuted,
            color: ch === "private" ? C.private : C.fgMuted,
            border: "none",
            borderRight: `1px solid ${C.border}`,
            cursor: "pointer",
            outline: "none",
          }}
        >
          <option value="public">Public</option>
          <option value="private">Whisper</option>
          {isDM && <option value="narrate">Narrate</option>}
        </select>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            ch === "private"
              ? "Private message..."
              : ch === "narrate"
                ? "Narration (typed)..."
                : "Message the table..."
          }
          style={{
            flex: 1,
            fontFamily: C.sans,
            fontSize: 14,
            padding: "10px 16px",
            background: "transparent",
            color: C.fg,
            border: "none",
            outline: "none",
          }}
        />
      </div>
    </div>
  );
};

// ========== DM: LIVE SESSION ==========
const DMLive = () => {
  const [turn, setTurn] = useState(3);
  const allF = Object.keys(CLS);
  const [af, setAf] = useState(allF);
  const toggle = (k) =>
    setAf((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const counts = {};
  FEED.forEach((i) => {
    if (i.cls) counts[i.cls] = (counts[i.cls] || 0) + 1;
  });
  const filtered = FEED.filter(
    (i) =>
      i.source === "roll" ||
      i.cls === "private" ||
      !i.cls ||
      af.includes(i.cls),
  );
  const all = [
    ...PLAYERS.map((p) => ({ ...p, type: "player" })),
    ...MONSTERS.map((m) => ({ ...m, type: "monster" })),
  ].sort((a, b) => b.init - a.init);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 320px",
        gap: 0,
        height: "calc(100vh - 140px)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          borderRight: `1px solid ${C.border}`,
          minHeight: 0,
        }}
      >
        <Filters active={af} onToggle={toggle} counts={counts} />
        <div style={{ flex: 1, overflow: "auto" }}>
          {filtered.map((i) => (
            <FeedItem key={i.id} item={i} isDM />
          ))}
        </div>
        <ChatInput isDM />
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <SBar right="Round 2">Initiative</SBar>
        {all.map((c, i) => (
          <div
            key={c.name}
            onClick={() => setTurn(i)}
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
              background: turn === i ? C.accentLight : "transparent",
              borderLeft:
                turn === i ? `3px solid ${C.accent}` : "3px solid transparent",
              cursor: "pointer",
            }}
          >
            <span
              style={{
                fontFamily: C.mono,
                fontSize: 13,
                fontWeight: 700,
                color: C.fgDim,
                minWidth: 22,
              }}
            >
              {c.init}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    fontFamily: C.sans,
                    fontSize: 14,
                    fontWeight: 600,
                    color: c.type === "monster" ? C.monster : C.fg,
                  }}
                >
                  {c.name}
                </span>
                <span
                  style={{ fontFamily: C.sans, fontSize: 12, color: C.fgDim }}
                >
                  {c.type === "player" ? `${c.class} ${c.level}` : `CR ${c.cr}`}
                </span>
                {c.conditions?.map((d) => (
                  <Pill
                    key={d}
                    color={d === "Poisoned" ? C.ok : C.warn}
                    bg={d === "Poisoned" ? C.okBg : C.warnBg}
                  >
                    {d}
                  </Pill>
                ))}
              </div>
              <HpBar current={c.hp} max={c.maxHp} size="small" />
            </div>
            <span style={{ fontFamily: C.mono, fontSize: 12, color: C.fgDim }}>
              AC {c.ac}
            </span>
          </div>
        ))}
        <div
          style={{
            padding: "8px 16px",
            display: "flex",
            gap: 6,
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          <button
            style={{
              flex: 1,
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              padding: 6,
              background: C.fg,
              color: C.bg,
              border: "none",
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            Next Turn
          </button>
          <button
            style={{
              fontFamily: C.sans,
              fontSize: 12,
              fontWeight: 500,
              padding: "6px 12px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            End Round
          </button>
        </div>
        <SBar right="4,102 / 8,192">LLM Context · Gemini Flash</SBar>
        {RAG.map((c, i) => (
          <div
            key={i}
            style={{
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
              opacity: c.rel > 0.7 ? 1 : 0.5,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 3,
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span
                  style={{
                    fontFamily: C.mono,
                    fontSize: 11,
                    color: C.accent,
                    fontWeight: 600,
                  }}
                >
                  {c.source}
                </span>
                <span
                  style={{ fontFamily: C.sans, fontSize: 13, fontWeight: 600 }}
                >
                  {c.title}
                </span>
              </div>
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                {c.auto && (
                  <Pill color={C.rules} bg={C.rulesBg}>
                    Auto
                  </Pill>
                )}
                {c.pinned && (
                  <Pill color={C.accent} bg={C.accentLight}>
                    📌
                  </Pill>
                )}
                <span
                  style={{ fontFamily: C.mono, fontSize: 10, color: C.fgDim }}
                >
                  {(c.rel * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div
              style={{
                fontFamily: C.sans,
                fontSize: 12,
                color: C.fgMuted,
                lineHeight: 1.5,
              }}
            >
              {c.text}
            </div>
          </div>
        ))}
        <div style={{ padding: "8px 12px" }}>
          <input
            placeholder="Ask a rule question..."
            style={{
              width: "100%",
              fontFamily: C.sans,
              fontSize: 13,
              padding: "8px 12px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>
      </div>
    </div>
  );
};

// ========== DM: PREP ==========
const DMPrep = () => (
  <div
    style={{
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 20,
      padding: 20,
    }}
  >
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card>
        <SBar right="Session 4">Planned Encounters</SBar>
        {PREP_ENC.map((e, i) => (
          <div
            key={i}
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
                style={{ fontFamily: C.sans, fontSize: 15, fontWeight: 600 }}
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
        {PLAYERS.map((p, i) => (
          <div
            key={i}
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
            <div style={{ fontFamily: C.mono, fontSize: 13, color: C.fgMuted }}>
              AC {p.ac} · HP {p.maxHp}
            </div>
          </div>
        ))}
      </Card>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card>
        <SBar>Session History</SBar>
        {SESSIONS.map((s, i) => (
          <div
            key={i}
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
                style={{ fontFamily: C.sans, fontSize: 14, fontWeight: 600 }}
              >
                Session {s.n}
              </span>
              <span
                style={{ fontFamily: C.mono, fontSize: 12, color: C.fgDim }}
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
        {[
          { k: "Location", v: "Triboar Trail → Cragmaw Hideout" },
          { k: "Quest", v: "Find Gundren Rockseeker, locate Wave Echo Cave" },
          {
            k: "Threats",
            v: "Cragmaw Goblins, Black Spider (unknown), Redbrand Ruffians",
          },
          {
            k: "Open Threads",
            v: "Redbrand hideout under Tresendar Manor. Old Owl Well miners.",
          },
        ].map((x, i) => (
          <div
            key={i}
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
              {x.k}
            </span>
            <span
              style={{
                fontFamily: C.sans,
                fontSize: 14,
                color: C.fg,
                lineHeight: 1.5,
              }}
            >
              {x.v}
            </span>
          </div>
        ))}
      </Card>
      <Card>
        <SBar>Rule Lookup</SBar>
        <div style={{ padding: "12px 20px" }}>
          <input
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

// ========== PLAYER: LIVE ==========
const PlayerLive = () => {
  const player = PLAYERS[3];
  const stats = [
    { n: "STR", m: 0 },
    { n: "DEX", m: 4 },
    { n: "CON", m: 1 },
    { n: "INT", m: 2 },
    { n: "WIS", m: 0 },
    { n: "CHA", m: 2 },
  ];
  const feed = FEED.filter(
    (i) =>
      i.cls !== "table_talk" && (i.cls !== "private" || i.private_to === "vex"),
  );
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 320px",
        gap: 0,
        height: "calc(100vh - 140px)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          borderRight: `1px solid ${C.border}`,
          minHeight: 0,
        }}
      >
        <div style={{ flex: 1, overflow: "auto" }}>
          {feed.map((i) => (
            <FeedItem key={i.id} item={i} showCls={false} />
          ))}
        </div>
        <ChatInput />
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: 8,
            }}
          >
            <div>
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 17,
                  fontWeight: 700,
                  color: player.color,
                }}
              >
                {player.name}
              </span>
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fgMuted,
                  marginLeft: 8,
                }}
              >
                {player.class} {player.level}
              </span>
            </div>
            <span
              style={{ fontFamily: C.mono, fontSize: 13, color: C.fgMuted }}
            >
              AC {player.ac}
            </span>
          </div>
          <HpBar current={player.hp} max={player.maxHp} />
          {player.conditions.length > 0 && (
            <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
              {player.conditions.map((c) => (
                <Pill key={c} color={C.warn} bg={C.warnBg}>
                  {c}
                </Pill>
              ))}
            </div>
          )}
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(6,1fr)",
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          {stats.map((s) => (
            <div
              key={s.n}
              style={{
                padding: "6px 0",
                textAlign: "center",
                borderRight: `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  fontFamily: C.sans,
                  fontSize: 9,
                  color: C.fgDim,
                  letterSpacing: 1,
                  textTransform: "uppercase",
                }}
              >
                {s.n}
              </div>
              <div
                style={{ fontFamily: C.mono, fontSize: 15, fontWeight: 700 }}
              >
                {s.m >= 0 ? "+" : ""}
                {s.m}
              </div>
            </div>
          ))}
        </div>
        <SBar>Quick Rolls</SBar>
        {[
          { l: "Shortsword", f: "1d20+7", s: "Attack" },
          { l: "Damage", f: "1d6+4", s: "Piercing" },
          { l: "Sneak Attack", f: "3d6", s: "Extra" },
          { l: "Stealth", f: "1d20+10", s: "Expertise" },
          { l: "Perception", f: "1d20+3", s: "Passive 13" },
        ].map((r) => (
          <button
            key={r.l}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              width: "100%",
              padding: "8px 16px",
              fontFamily: C.sans,
              fontSize: 13,
              background: "transparent",
              color: C.fg,
              border: "none",
              borderBottom: `1px solid ${C.border}`,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <div>
              <span style={{ fontWeight: 500 }}>{r.l}</span>
              <span style={{ fontSize: 11, color: C.fgDim, marginLeft: 6 }}>
                {r.s}
              </span>
            </div>
            <span
              style={{ fontFamily: C.mono, fontSize: 12, color: C.fgMuted }}
            >
              {r.f}
            </span>
          </button>
        ))}
        <div style={{ padding: "8px 12px" }}>
          <input
            placeholder="Custom: 2d6+3"
            style={{
              width: "100%",
              fontFamily: C.mono,
              fontSize: 12,
              padding: "7px 10px",
              background: C.bgMuted,
              color: C.fg,
              border: `1px solid ${C.border}`,
              borderRadius: 3,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>
        <SBar>Known Lore</SBar>
        {[
          {
            fact: "Goblin boss called for cave reinforcements in Goblin.",
            src: "Overheard, Session 4",
            isNew: true,
          },
          {
            fact: "Cragmaw goblins act under orders from 'the Black Spider.'",
            src: "Goblin prisoner",
          },
          {
            fact: "Gundren taken to 'the castle' — location unknown.",
            src: "Session 3",
          },
        ].map((x, i) => (
          <div
            key={i}
            style={{
              padding: "8px 16px",
              borderBottom: `1px solid ${C.border}`,
            }}
          >
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {x.isNew && (
                <Pill color={C.accent} bg={C.accentLight}>
                  New
                </Pill>
              )}
              <span
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  color: C.fg,
                  lineHeight: 1.5,
                }}
              >
                {x.fact}
              </span>
            </div>
            <div
              style={{
                fontFamily: C.mono,
                fontSize: 10,
                color: C.fgDim,
                marginTop: 3,
              }}
            >
              {x.src}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ========== PLAYER: CHARACTER ==========
const PlayerChar = () => {
  const player = PLAYERS[3];
  const stats = [
    { n: "STR", v: 10, m: 0 },
    { n: "DEX", v: 18, m: 4 },
    { n: "CON", v: 12, m: 1 },
    { n: "INT", v: 14, m: 2 },
    { n: "WIS", v: 10, m: 0 },
    { n: "CHA", v: 14, m: 2 },
  ];
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 20,
        padding: 20,
      }}
    >
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
                style={{ fontFamily: C.mono, fontSize: 14, color: C.fgMuted }}
              >
                AC {player.ac} · HP {player.maxHp}
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3,1fr)",
                gap: 8,
              }}
            >
              {stats.map((s) => (
                <div
                  key={s.n}
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
                    {s.n}
                  </div>
                  <div
                    style={{
                      fontFamily: C.mono,
                      fontSize: 24,
                      fontWeight: 700,
                    }}
                  >
                    {s.m >= 0 ? "+" : ""}
                    {s.m}
                  </div>
                  <div
                    style={{ fontFamily: C.mono, fontSize: 13, color: C.fgDim }}
                  >
                    {s.v}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
        <Card>
          <SBar>Inventory</SBar>
          {[
            { n: "Shortsword", d: "1d6 piercing, finesse, light", eq: true },
            { n: "Shortbow", d: "1d6 piercing, range 80/320", eq: true },
            { n: "Leather Armor", d: "AC 11 + Dex modifier", eq: true },
            { n: "Thieves' Tools", d: "Proficient", eq: false },
          ].map((x, i) => (
            <div
              key={i}
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
                  style={{ fontFamily: C.sans, fontSize: 14, fontWeight: 500 }}
                >
                  {x.n}
                </span>
                <div
                  style={{
                    fontFamily: C.sans,
                    fontSize: 12,
                    color: C.fgDim,
                    marginTop: 2,
                  }}
                >
                  {x.d}
                </div>
              </div>
              {x.eq && (
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
            47 gp · 12 sp · 3 cp
          </div>
        </Card>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <Card>
          <SBar>Journal</SBar>
          {[
            {
              n: 3,
              d: "Feb 9",
              t: "Ambushed by goblins. Spotted the ambush — 24 Perception. Took two out from the trees. Captured one: Cragmaw Cave, 'the Black Spider,' Gundren taken to a castle.",
            },
            {
              n: 2,
              d: "Feb 2",
              t: "Phandalin. Pickpocketed Redbrand leader's note — 'Glasstaff' at Tresendar Manor.",
            },
          ].map((s, i) => (
            <div
              key={i}
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
                  style={{ fontFamily: C.sans, fontSize: 14, fontWeight: 600 }}
                >
                  Session {s.n}
                </span>
                <span
                  style={{ fontFamily: C.mono, fontSize: 12, color: C.fgDim }}
                >
                  {s.d}
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
                {s.t}
              </div>
            </div>
          ))}
        </Card>
        <Card>
          <SBar>Known Lore</SBar>
          {[
            {
              f: "Gundren Rockseeker hired the party for Phandalin escort.",
              s: "Session 1",
            },
            { f: "Cragmaw goblins serve 'the Black Spider.'", s: "Session 3" },
            {
              f: "Gundren taken to 'the castle' — unknown location.",
              s: "Goblin prisoner",
            },
            {
              f: "'Glasstaff' leads Redbrands from Tresendar Manor.",
              s: "Pickpocketed note",
            },
          ].map((x, i) => (
            <div
              key={i}
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
                {x.f}
              </div>
              <div
                style={{
                  fontFamily: C.mono,
                  fontSize: 11,
                  color: C.fgDim,
                  marginTop: 4,
                }}
              >
                Source: {x.s}
              </div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
};

// ========== MAIN ==========
export default function Grimoire() {
  const [role, setRole] = useState("dm");
  const [dmTab, setDmTab] = useState("session");
  const [pTab, setPTab] = useState("session");
  const isLive =
    (role === "dm" && dmTab === "session") ||
    (role === "player" && pTab === "session");

  return (
    <div
      style={{
        background: C.bg,
        color: C.fg,
        minHeight: "100vh",
        fontFamily: C.sans,
      }}
    >
      <div
        style={{
          background: C.bgCard,
          borderBottom: `1px solid ${C.border}`,
          padding: "0 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <span
            style={{
              fontFamily: C.mono,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: 2,
              padding: "14px 0",
            }}
          >
            GRIMOIRE
          </span>
          <div style={{ display: "flex", gap: 0 }}>
            {[
              { k: "dm", l: "DM" },
              { k: "player", l: "Player" },
            ].map((r) => (
              <button
                key={r.k}
                onClick={() => setRole(r.k)}
                style={{
                  fontFamily: C.sans,
                  fontSize: 13,
                  fontWeight: role === r.k ? 600 : 400,
                  padding: "14px 16px",
                  background: "none",
                  border: "none",
                  borderBottom:
                    role === r.k
                      ? `2px solid ${C.fg}`
                      : "2px solid transparent",
                  color: role === r.k ? C.fg : C.fgMuted,
                  cursor: "pointer",
                }}
              >
                {r.l}
              </button>
            ))}
          </div>
        </div>
        <div style={{ fontFamily: C.sans, fontSize: 13, color: C.fgMuted }}>
          Lost Mine of Phandelver — Session 4
        </div>
      </div>
      <div style={{ background: C.bgCard, paddingLeft: 20 }}>
        {role === "dm" ? (
          <TabBar
            tabs={[
              { key: "session", label: "Live Session" },
              { key: "prep", label: "Session Prep" },
            ]}
            active={dmTab}
            onSelect={setDmTab}
          />
        ) : (
          <TabBar
            tabs={[
              { key: "session", label: "Live Session" },
              { key: "character", label: "Character" },
            ]}
            active={pTab}
            onSelect={setPTab}
          />
        )}
      </div>
      {isLive && <VoiceBar />}
      {role === "dm" && dmTab === "session" && <DMLive />}
      {role === "dm" && dmTab === "prep" && <DMPrep />}
      {role === "player" && pTab === "session" && <PlayerLive />}
      {role === "player" && pTab === "character" && <PlayerChar />}
    </div>
  );
}

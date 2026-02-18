import { useState, useEffect, useRef, useCallback } from "react";
import { Mic, MicOff, ChevronDown, ChevronUp, ChevronRight, Check, Zap, AlertTriangle, Volume2, Terminal, Plus, X, Maximize2, Minimize2, PanelRightOpen, PanelRightClose, GitBranch, FileCode, Play, MoreHorizontal, Circle, Settings } from "lucide-react";

/*
  LAYOUT STRATEGY (Staff UX Researcher + Staff Frontend Eng)
  ──────────────────────────────────────────────────────────

  DESKTOP (>=1080px):
  ┌──────────┬───────────────────────────┬──────────────────┐
  │ Sessions │      Transcript           │  Detail Panel    │
  │  Rail    │   (voice-first chat)      │ (diffs, output,  │
  │  200px   │   centered, max 720px     │  diagrams)       │
  │          │                           │  ~420px          │
  └──────────┴───────────────────────────┴──────────────────┘
  
  - Transcript stays clean/conversational, inline artifacts are compact cards
  - Clicking a card opens it full-size in the detail panel (code review friendly)
  - Detail panel is toggleable — close it for focused conversation mode
  - Voice controls: persistent top bar

  MOBILE (<768px):
  ┌─────────────────────┐
  │  Header + session   │
  │─────────────────────│
  │                     │
  │    Transcript       │
  │  (single column,    │
  │   artifacts inline) │
  │                     │
  │─────────────────────│
  │  Input bar          │
  │─────────────────────│
  │        🎤 FAB       │
  └─────────────────────┘

  - Sessions in dropdown
  - Artifacts expand inline
  - Mic is a floating action button (bottom right)
  - No detail panel
*/

// ── Responsive hook ────────────────────────────────────────────────────────
function useBreakpoint() {
  const [bp, setBp] = useState(() => {
    if (typeof window === "undefined") return "desktop";
    return window.innerWidth < 768 ? "mobile" : "desktop";
  });
  useEffect(() => {
    const check = () => setBp(window.innerWidth < 768 ? "mobile" : "desktop");
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return bp;
}

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg: "#FFFFFF",
  bgSub: "#FAFAFA",
  surface: "#F4F4F5",
  surfaceHover: "#EBEBED",
  border: "#E4E4E7",
  borderLight: "#F0F0F2",
  text: "#18181B",
  textSec: "#52525B",
  textTer: "#A1A1AA",
  textFaint: "#D4D4D8",
  you: "#047857",
  youBg: "#ECFDF5",
  youBorder: "#A7F3D0",
  voice: "#7C3AED",
  voiceBg: "#F5F3FF",
  voiceBorder: "#DDD6FE",
  ccBg: "#FAFAFA",
  approval: "#B45309",
  approvalBg: "#FFFBEB",
  approvalBorder: "#FDE68A",
  success: "#059669",
  danger: "#DC2626",
  micOn: "#DC2626",
  addGreen: "#16A34A",
  addBg: "#F0FDF4",
  delRed: "#DC2626",
  delBg: "#FEF2F2",
  accentBlue: "#2563EB",
};

const sans = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const mono = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace";

// ── Mock data ──────────────────────────────────────────────────────────────
const SESSIONS = [
  { id: "s1", name: "semgrep-infra", status: "active", turns: 12, ts: "2m ago" },
  { id: "s2", name: "cloudflare-operator", status: "idle", turns: 8, ts: "3h ago" },
  { id: "s3", name: "homelab-argocd", status: "idle", turns: 23, ts: "yesterday" },
];

function makeDiff() {
  const ib = String.fromCharCode(105, 109, 112, 111, 114, 116);
  return [
    { t: "h", x: "--- a/src/k8s/client.ts" },
    { t: "h", x: "+++ b/src/k8s/client.ts" },
    { t: "c", x: " " + ib + " { KubeConfig, CoreV1Api };" },
    { t: "+", x: "+" + ib + " { setTimeout };" },
    { t: "c", x: "" },
    { t: "c", x: " export class K8sClient {" },
    { t: "+", x: "+  private readonly MAX_RETRIES = 5;" },
    { t: "+", x: "+  private readonly BASE_DELAY = 1000;" },
    { t: "+", x: "+  private readonly MAX_DELAY = 30000;" },
    { t: "c", x: "" },
    { t: "c", x: "   private api: CoreV1Api;" },
    { t: "c", x: "" },
    { t: "-", x: "-  async getPods(ns: string) {" },
    { t: "-", x: "-    const res = await this.api.listNamespacedPod(ns);" },
    { t: "-", x: "-    return res.body.items;" },
    { t: "-", x: "-  }" },
    { t: "+", x: "+  private async withRetry<T>(fn: () => Promise<T>): Promise<T> {" },
    { t: "+", x: "+    for (let i = 0; i < this.MAX_RETRIES; i++) {" },
    { t: "+", x: "+      try {" },
    { t: "+", x: "+        return await fn();" },
    { t: "+", x: "+      } catch (err) {" },
    { t: "+", x: "+        if (i === this.MAX_RETRIES - 1) throw err;" },
    { t: "+", x: "+        const base = this.BASE_DELAY * Math.pow(2, i);" },
    { t: "+", x: "+        const capped = Math.min(base, this.MAX_DELAY);" },
    { t: "+", x: "+        const jitter = capped * (0.75 + Math.random() * 0.5);" },
    { t: "+", x: "+        await setTimeout(jitter);" },
    { t: "+", x: "+      }" },
    { t: "+", x: "+    }" },
    { t: "+", x: "+    throw new Error('unreachable');" },
    { t: "+", x: "+  }" },
    { t: "+", x: "" },
    { t: "+", x: "+  async getPods(ns: string) {" },
    { t: "+", x: "+    return this.withRetry(async () => {" },
    { t: "+", x: "+      const res = await this.api.listNamespacedPod(ns);" },
    { t: "+", x: "+      return res.body.items;" },
    { t: "+", x: "+    });" },
    { t: "+", x: "+  }" },
    { t: "c", x: " }" },
  ];
}

const TEST_OUTPUT = "PASS src/k8s/__tests__/client.test.ts\n  K8sClient retry logic\n    \u2713 retries on 503 errors (234ms)\n    \u2713 gives up after MAX_RETRIES (89ms)\n    \u2713 jitter within \u00b125% bounds (156ms)\n    \u2713 no retry on success (12ms)\n\nTests: 4 passed, 4 total\nTime:  1.423s";

const MERMAID_CODE = "sequenceDiagram\n    participant Test\n    participant Client\n    participant K8sAPI\n    Test->>Client: getPods(\"default\")\n    Client->>K8sAPI: listNamespacedPod\n    K8sAPI-->>Client: 503 Service Unavailable\n    Note over Client: Wait ~1s + jitter\n    Client->>K8sAPI: retry 1\n    K8sAPI-->>Client: 503\n    Note over Client: Wait ~2s + jitter\n    Client->>K8sAPI: retry 2\n    K8sAPI-->>Client: 200 OK\n    Client-->>Test: Pod[]";

const TRANSCRIPT = [
  { id: 1, role: "voice", time: "14:23", text: "Add retry logic to the Kubernetes client with exponential backoff and jitter" },
  { id: 2, role: "claude", time: "14:23", status: "thinking", text: "Analysing src/k8s/client.ts..." },
  { id: 3, role: "claude", time: "14:24", status: "tool", text: "Editing src/k8s/client.ts" },
  {
    id: 5, role: "claude", time: "14:25", status: "done",
    text: "Added exponential backoff with jitter. Base delay 1s, max 30s, \u00b125% jitter. All API calls now go through withRetry().",
    artifact: { type: "diff", label: "client.ts", data: makeDiff(), additions: 22, deletions: 4 },
  },
  { id: 6, role: "gemini", time: "14:25", text: "Done \u2014 added exponential backoff with jitter to the K8s client. Base delay one second, max thirty, with twenty-five percent jitter. One file updated." },
  { id: 7, role: "voice", time: "14:26", text: "Now add tests for that retry logic" },
  { id: 8, role: "claude", time: "14:26", status: "thinking", text: "Creating test file..." },
  { id: 9, role: "claude", time: "14:27", status: "tool", text: "Created client.test.ts" },
  { id: 10, role: "claude", time: "14:27", status: "approval", text: "Run: npm test -- --testPathPattern=k8s/client" },
  { id: 12, role: "voice", time: "14:28", text: "Yeah go ahead" },
  {
    id: 13, role: "claude", time: "14:28", status: "done",
    text: "4 tests passing \u2014 retries, max limit, jitter bounds, and happy path.",
    artifact: { type: "output", label: "test results", data: TEST_OUTPUT },
    artifact2: { type: "mermaid", label: "retry sequence", data: MERMAID_CODE },
  },
  { id: 14, role: "gemini", time: "14:28", text: "All four tests are green \u2014 retries, max limit, jitter bounds, and the happy path all passing." },
];

// ── Shared Components ──────────────────────────────────────────────────────

function VoiceDot({ state, size }) {
  const sz = size || 8;
  const color = state === "speaking" ? C.voice : state === "listening" ? C.success : C.textFaint;
  return (
    <div style={{ position: "relative", width: sz, height: sz, flexShrink: 0 }}>
      <div style={{ width: sz, height: sz, borderRadius: "50%", backgroundColor: color, transition: "background-color 200ms" }} />
      {state !== "off" && (
        <div style={{
          position: "absolute", inset: -3, borderRadius: "50%",
          border: `1.5px solid ${color}`, opacity: 0.35,
          animation: "vcc-ring 2s ease-out infinite",
        }} />
      )}
    </div>
  );
}

function ArtifactCard({ artifact, onClick, selected }) {
  if (!artifact) return null;
  const icons = { diff: <FileCode size={13} />, output: <Terminal size={13} />, mermaid: <GitBranch size={13} /> };
  return (
    <button onClick={onClick} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "5px 10px", borderRadius: 6, cursor: "pointer",
      border: selected ? `1.5px solid ${C.accentBlue}` : `1px solid ${C.border}`,
      backgroundColor: selected ? "#EFF6FF" : C.surface,
      fontFamily: mono, fontSize: 12, color: selected ? C.accentBlue : C.textSec,
      marginTop: 6, marginRight: 6, transition: "all 150ms",
    }}>
      {icons[artifact.type]}
      <span>{artifact.label}</span>
      {artifact.additions > 0 && <span style={{ color: C.addGreen }}>+{artifact.additions}</span>}
      {artifact.deletions > 0 && <span style={{ color: C.delRed }}>{"-"}{artifact.deletions}</span>}
    </button>
  );
}

function InlineArtifact({ artifact }) {
  const [open, setOpen] = useState(false);
  if (!artifact) return null;

  if (artifact.type === "diff") {
    const lines = artifact.data;
    const show = open ? lines : lines.slice(0, 8);
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <button onClick={() => setOpen(!open)} style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px 12px", backgroundColor: C.surface, border: "none",
          borderBottom: `1px solid ${C.border}`, cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <FileCode size={13} />
            <span style={{ fontFamily: mono }}>{artifact.label}</span>
            {artifact.additions > 0 && <span style={{ color: C.addGreen, fontFamily: mono, fontSize: 11 }}>+{artifact.additions}</span>}
            {artifact.deletions > 0 && <span style={{ color: C.delRed, fontFamily: mono, fontSize: 11 }}>{"-"}{artifact.deletions}</span>}
          </span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <div style={{ padding: "6px 0", overflowX: "auto", fontFamily: mono, fontSize: 12, lineHeight: 1.7 }}>
          {show.map((l, i) => (
            <div key={i} style={{
              padding: "0 12px", whiteSpace: "pre",
              color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
              backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
            }}>{l.x}</div>
          ))}
          {!open && lines.length > 8 && (
            <div style={{ padding: "4px 12px", fontSize: 11, color: C.textTer }}>+{lines.length - 8} more lines</div>
          )}
        </div>
      </div>
    );
  }
  if (artifact.type === "output") {
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "7px 12px", backgroundColor: C.surface, borderBottom: `1px solid ${C.border}`, fontSize: 12, color: C.textSec, display: "flex", alignItems: "center", gap: 6 }}>
          <Terminal size={13} /> {artifact.label}
        </div>
        <pre style={{ padding: "8px 12px", margin: 0, overflowX: "auto", fontFamily: mono, fontSize: 12, lineHeight: 1.6, color: C.text }}>{artifact.data}</pre>
      </div>
    );
  }
  if (artifact.type === "mermaid") {
    return (
      <div style={{ marginTop: 6, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
        <button onClick={() => setOpen(!open)} style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px 12px", backgroundColor: C.surface, border: "none",
          borderBottom: open ? `1px solid ${C.border}` : "none", cursor: "pointer", fontFamily: sans, fontSize: 12, color: C.textSec,
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><GitBranch size={13} /> {artifact.label}</span>
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {open && <pre style={{ padding: "8px 12px", margin: 0, overflowX: "auto", fontFamily: mono, fontSize: 11, lineHeight: 1.5, color: C.you }}>{artifact.data}</pre>}
      </div>
    );
  }
  return null;
}

// ── Detail Panel (desktop only) ────────────────────────────────────────────
function DetailPanel({ artifact, onClose }) {
  if (!artifact) return (
    <div style={{
      height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
      color: C.textFaint, fontFamily: sans, fontSize: 13,
      flexDirection: "column", gap: 8, padding: 32,
      textAlign: "center",
    }}>
      <FileCode size={32} color={C.textFaint} strokeWidth={1.2} />
      <span>Select a diff, output, or diagram to inspect it here</span>
    </div>
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {artifact.type === "diff" && <FileCode size={14} color={C.textSec} />}
          {artifact.type === "output" && <Terminal size={14} color={C.textSec} />}
          {artifact.type === "mermaid" && <GitBranch size={14} color={C.textSec} />}
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: sans }}>{artifact.label}</span>
          {artifact.additions > 0 && <span style={{ fontSize: 12, color: C.addGreen, fontFamily: mono }}>+{artifact.additions}</span>}
          {artifact.deletions > 0 && <span style={{ fontSize: 12, color: C.delRed, fontFamily: mono }}>{"-"}{artifact.deletions}</span>}
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.textTer, padding: 4, display: "flex" }}>
          <X size={16} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
        {artifact.type === "diff" && (
          <div style={{ fontFamily: mono, fontSize: 13, lineHeight: 1.8, minWidth: "fit-content" }}>
            {artifact.data.map((l, i) => (
              <div key={i} style={{
                padding: "0 16px", whiteSpace: "pre",
                color: l.t === "+" ? C.addGreen : l.t === "-" ? C.delRed : l.t === "h" ? C.textTer : C.textSec,
                backgroundColor: l.t === "+" ? C.addBg : l.t === "-" ? C.delBg : "transparent",
              }}>{l.x}</div>
            ))}
          </div>
        )}
        {artifact.type === "output" && (
          <pre style={{ padding: "12px 16px", margin: 0, fontFamily: mono, fontSize: 13, lineHeight: 1.7, color: C.text, whiteSpace: "pre-wrap" }}>{artifact.data}</pre>
        )}
        {artifact.type === "mermaid" && (
          <pre style={{ padding: "12px 16px", margin: 0, fontFamily: mono, fontSize: 12, lineHeight: 1.6, color: C.you }}>{artifact.data}</pre>
        )}
      </div>
    </div>
  );
}

// ── Message grouping + rendering ───────────────────────────────────────────
function useGroups(messages) {
  const groups = [];
  let cur = null;
  messages.forEach(m => {
    if (m.role === "voice") {
      if (cur) groups.push(cur);
      cur = { voice: m, steps: [], result: null, summary: null, approval: null };
    } else if (m.role === "claude") {
      if (!cur) cur = { voice: null, steps: [], result: null, summary: null, approval: null };
      if (m.status === "thinking" || m.status === "tool") cur.steps.push(m);
      else if (m.status === "approval") cur.approval = m;
      else if (m.status === "done") cur.result = m;
    } else if (m.role === "gemini") {
      if (cur) { cur.summary = m; groups.push(cur); cur = null; }
    }
  });
  if (cur) groups.push(cur);
  return groups;
}

function TranscriptView({ messages, onSelectArtifact, selectedArtifactId, isMobile }) {
  const groups = useGroups(messages);
  const [expandedSteps, setExpandedSteps] = useState({});

  return (
    <div>
      {groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 28 }}>
          {/* Voice input */}
          {g.voice && (
            <div style={{
              padding: "12px 16px", marginBottom: 10,
              backgroundColor: C.youBg, borderRadius: 12,
              borderLeft: `3px solid ${C.you}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                <Mic size={13} color={C.you} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.you }}>You</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.voice.time}</span>
              </div>
              <div style={{ fontSize: 15, color: C.text, lineHeight: 1.55 }}>{g.voice.text}</div>
            </div>
          )}

          {/* Collapsed intermediate steps */}
          {g.steps.length > 0 && (
            <button
              onClick={() => setExpandedSteps(p => ({ ...p, [gi]: !p[gi] }))}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "3px 0", margin: "2px 0 6px",
                background: "none", border: "none", cursor: "pointer",
                fontFamily: sans, fontSize: 12, color: C.textTer,
              }}
            >
              {expandedSteps[gi] ? <ChevronUp size={12} /> : <ChevronRight size={12} />}
              <MoreHorizontal size={12} />
              <span>{g.steps.length} step{g.steps.length > 1 ? "s" : ""}</span>
              {expandedSteps[gi] && (
                <span style={{ marginLeft: 4, color: C.textTer }}>
                  {g.steps.map(s => s.text).join(" \u2192 ")}
                </span>
              )}
            </button>
          )}

          {/* Approval */}
          {g.approval && (
            <div style={{
              margin: "8px 0", padding: "12px 16px",
              backgroundColor: C.approvalBg, border: `1px solid ${C.approvalBorder}`,
              borderRadius: 10, display: "flex", alignItems: "center", gap: 12,
              flexWrap: "wrap",
            }}>
              <AlertTriangle size={16} color={C.approval} style={{ flexShrink: 0 }} />
              <span style={{ fontFamily: mono, fontSize: 13, color: C.text, flex: 1, minWidth: 160 }}>{g.approval.text}</span>
              <div style={{ display: "flex", gap: 8 }}>
                <button style={{
                  padding: "7px 20px", borderRadius: 7, border: "none", cursor: "pointer",
                  backgroundColor: C.text, color: C.bg, fontFamily: sans, fontSize: 13, fontWeight: 500,
                }}>Approve</button>
                <button style={{
                  padding: "7px 20px", borderRadius: 7, cursor: "pointer",
                  backgroundColor: "transparent", color: C.textSec,
                  border: `1px solid ${C.border}`, fontFamily: sans, fontSize: 13,
                }}>Reject</button>
              </div>
            </div>
          )}

          {/* Claude Code result */}
          {g.result && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <Check size={13} color={C.success} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.textSec }}>Claude Code</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.result.time}</span>
              </div>
              <div style={{ fontSize: 14, color: C.textSec, lineHeight: 1.55 }}>{g.result.text}</div>

              {/* Artifact cards on desktop, inline on mobile */}
              {isMobile ? (
                <>
                  {g.result.artifact && <InlineArtifact artifact={g.result.artifact} />}
                  {g.result.artifact2 && <InlineArtifact artifact={g.result.artifact2} />}
                </>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 0 }}>
                  {g.result.artifact && (
                    <ArtifactCard
                      artifact={g.result.artifact}
                      selected={selectedArtifactId === g.result.id + "-1"}
                      onClick={() => onSelectArtifact(g.result.artifact, g.result.id + "-1")}
                    />
                  )}
                  {g.result.artifact2 && (
                    <ArtifactCard
                      artifact={g.result.artifact2}
                      selected={selectedArtifactId === g.result.id + "-2"}
                      onClick={() => onSelectArtifact(g.result.artifact2, g.result.id + "-2")}
                    />
                  )}
                </div>
              )}
            </div>
          )}

          {/* Voice summary */}
          {g.summary && (
            <div style={{
              padding: "12px 16px",
              backgroundColor: C.voiceBg, borderRadius: 12,
              borderLeft: `3px solid ${C.voice}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                <Volume2 size={13} color={C.voice} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.voice }}>Spoken</span>
                <span style={{ fontSize: 12, color: C.textTer }}>{g.summary.time}</span>
              </div>
              <div style={{ fontSize: 14, color: C.text, lineHeight: 1.55, fontStyle: "italic" }}>{g.summary.text}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────
export default function App() {
  const bp = useBreakpoint();
  const [on, setOn] = useState(false);
  const [tx, setTx] = useState(false);
  const [sess, setSess] = useState("s1");
  const [showSess, setShowSess] = useState(false);
  const [inp, setInp] = useState("");
  const [detailArtifact, setDetailArtifact] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [showDetail, setShowDetail] = useState(true);
  const [showRail, setShowRail] = useState(true);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, []);

  useEffect(() => {
    if (!on) { setTx(false); return; }
    const id = setInterval(() => setTx(Math.random() > 0.55), 1800);
    return () => clearInterval(id);
  }, [on]);

  const s = SESSIONS.find(x => x.id === sess);
  const voiceState = !on ? "off" : tx ? "speaking" : "listening";

  const handleSelectArtifact = useCallback((artifact, id) => {
    if (detailId === id) { setDetailArtifact(null); setDetailId(null); }
    else { setDetailArtifact(artifact); setDetailId(id); setShowDetail(true); }
  }, [detailId]);

  // ── Mobile layout ──────────────────────────────────────────────
  if (bp === "mobile") {
    return (
      <div style={{ width: "100vw", height: "100vh", backgroundColor: C.bg, fontFamily: sans, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Mobile header */}
        <div style={{ display: "flex", alignItems: "center", padding: "0 12px", height: 52, borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 8 }}>
          <div style={{ position: "relative", flex: 1 }}>
            <button onClick={() => setShowSess(!showSess)} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "6px 10px", borderRadius: 8,
              border: `1px solid ${C.border}`, backgroundColor: C.bg, cursor: "pointer", fontFamily: sans, fontSize: 14, color: C.text,
            }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: s?.status === "active" ? C.success : C.textFaint }} />
              <span style={{ fontWeight: 500 }}>{s?.name}</span>
              <ChevronDown size={14} color={C.textTer} />
            </button>
            {showSess && (
              <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 4, backgroundColor: C.bg, border: `1px solid ${C.border}`, borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.1)", width: 220, zIndex: 100 }}>
                {SESSIONS.map(x => (
                  <button key={x.id} onClick={() => { setSess(x.id); setShowSess(false); }} style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", border: "none", backgroundColor: x.id === sess ? C.surface : C.bg, cursor: "pointer", fontFamily: sans, textAlign: "left" }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: x.status === "active" ? C.success : C.textFaint }} />
                    <div>
                      <div style={{ fontSize: 14, fontWeight: x.id === sess ? 600 : 400, color: C.text }}>{x.name}</div>
                      <div style={{ fontSize: 11, color: C.textTer }}>{x.turns} turns</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <VoiceDot state={voiceState} size={8} />
          <span style={{ fontSize: 12, color: voiceState === "off" ? C.textTer : C.textSec }}>{voiceState === "off" ? "" : voiceState === "listening" ? "Listening" : "Speaking"}</span>
        </div>

        <div ref={scrollRef} onClick={() => setShowSess(false)} style={{ flex: 1, overflowY: "auto", padding: "16px 12px 120px" }}>
          <TranscriptView messages={TRANSCRIPT} onSelectArtifact={() => {}} selectedArtifactId={null} isMobile />
          {on && (
            <div style={{ padding: "12px 0", display: "flex", alignItems: "center", gap: 8 }}>
              <VoiceDot state={voiceState} size={6} />
              <span style={{ fontSize: 13, color: C.textSec }}>{tx ? "Speaking..." : "Listening..."}</span>
            </div>
          )}
        </div>

        <div style={{ borderTop: `1px solid ${C.border}`, padding: "8px 12px", backgroundColor: C.bg, flexShrink: 0, display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", border: `1px solid ${C.border}`, borderRadius: 10, padding: "0 12px", height: 40, backgroundColor: C.surface }}>
            <input value={inp} onChange={e => setInp(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && inp.trim()) setInp(""); }} onFocus={() => setShowSess(false)} placeholder="Type a message..." style={{ flex: 1, backgroundColor: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14, fontFamily: sans }} />
          </div>
          <button onClick={() => setOn(!on)} style={{
            width: 44, height: 44, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0,
            border: on ? `2px solid ${C.micOn}` : `2px solid ${C.textFaint}`,
            backgroundColor: on ? "#FEF2F2" : C.bg,
          }}>
            {on ? <Mic size={18} color={C.micOn} /> : <MicOff size={18} color={C.textTer} />}
          </button>
        </div>

        <style>{`@keyframes vcc-ring{0%{transform:scale(1);opacity:.35}100%{transform:scale(1.8);opacity:0}} *{box-sizing:border-box;margin:0;padding:0} input::placeholder{color:${C.textFaint}}`}</style>
      </div>
    );
  }

  // ── Desktop layout ─────────────────────────────────────────────
  const hasDetail = showDetail && detailArtifact;

  return (
    <div style={{ width: "100vw", height: "100vh", backgroundColor: C.bg, fontFamily: sans, display: "flex", overflow: "hidden" }}>

      {/* Sessions rail */}
      {showRail && (
        <div style={{
          width: 220, flexShrink: 0, borderRight: `1px solid ${C.border}`,
          display: "flex", flexDirection: "column", backgroundColor: C.bgSub,
        }}>
          {/* Rail header: brand + collapse + new session */}
          <div style={{ padding: "14px 12px 10px", borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text, letterSpacing: 0.5 }}>Voice::CC</div>
                <div style={{ fontSize: 11, color: C.textTer, marginTop: 1 }}>Claude Code + Gemini</div>
              </div>
              <button onClick={() => setShowRail(false)} style={{
                background: "none", border: "none", cursor: "pointer", color: C.textTer,
                padding: 4, display: "flex", borderRadius: 6,
              }} title="Collapse sidebar">
                <PanelRightClose size={16} style={{ transform: "scaleX(-1)" }} />
              </button>
            </div>
            <button style={{
              width: "100%", padding: "8px 0", borderRadius: 8,
              border: "none", backgroundColor: C.text, color: C.bg,
              cursor: "pointer", fontSize: 12, fontFamily: sans, fontWeight: 500,
              display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
            }}>
              <Plus size={13} /> New session
            </button>
          </div>

          {/* Session list */}
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
            {SESSIONS.map(x => (
              <button key={x.id} onClick={() => setSess(x.id)} style={{
                width: "100%", textAlign: "left", padding: "10px 10px", borderRadius: 8,
                display: "flex", alignItems: "center", gap: 10,
                border: "none", cursor: "pointer", fontFamily: sans,
                backgroundColor: x.id === sess ? C.bg : "transparent",
                boxShadow: x.id === sess ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "background-color 100ms",
                marginBottom: 2,
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: x.status === "active" ? C.success : C.textFaint,
                }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: x.id === sess ? 600 : 400, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.name}</div>
                  <div style={{ fontSize: 11, color: C.textTer }}>{x.ts} \u00b7 {x.turns}t</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main column */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Top bar */}
        <div style={{
          display: "flex", alignItems: "center", padding: "0 20px",
          height: 52, borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 12,
        }}>
          {/* Rail open button (only when rail is hidden) */}
          {!showRail && (
            <button onClick={() => setShowRail(true)} style={{
              background: "none", border: "none", cursor: "pointer",
              color: C.textTer, padding: 4, display: "flex", borderRadius: 6,
            }} title="Show sessions">
              <PanelRightOpen size={18} style={{ transform: "scaleX(-1)" }} />
            </button>
          )}

          <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>{s?.name}</span>
          <span style={{
            fontSize: 11, color: C.textTer, fontFamily: mono,
            backgroundColor: C.surface, padding: "3px 8px", borderRadius: 5,
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <Terminal size={10} /> tmux
          </span>

          <div style={{ flex: 1 }} />

          <VoiceDot state={voiceState} size={9} />
          <span style={{ fontSize: 13, color: voiceState === "off" ? C.textTer : C.textSec, minWidth: 70 }}>
            {voiceState === "off" ? "Mic off" : voiceState === "listening" ? "Listening" : "Speaking"}
          </span>

          <button onClick={() => setOn(!on)} style={{
            width: 44, height: 44, borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", position: "relative", transition: "all 200ms",
            border: on ? `2px solid ${C.micOn}` : `2px solid ${C.textFaint}`,
            backgroundColor: on ? "#FEF2F2" : C.bg,
          }}>
            {on ? <Mic size={18} color={C.micOn} /> : <MicOff size={18} color={C.textTer} />}
            {on && (
              <div style={{
                position: "absolute", inset: -4, borderRadius: "50%",
                border: `2px solid ${C.micOn}`, opacity: 0.25,
                animation: "vcc-ring 2s ease-out infinite",
              }} />
            )}
          </button>

          <div style={{ width: 1, height: 24, backgroundColor: C.border, margin: "0 4px" }} />

          <button onClick={() => setShowDetail(!showDetail)} style={{
            background: "none", border: "none", cursor: "pointer",
            color: showDetail ? C.accentBlue : C.textTer, padding: 6, display: "flex",
            borderRadius: 6,
          }} title={showDetail ? "Hide detail panel" : "Show detail panel"}>
            {showDetail ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
          </button>
        </div>

        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {/* Transcript */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <div ref={scrollRef} onClick={() => setShowSess(false)} style={{
              flex: 1, overflowY: "auto", padding: "24px 32px 100px",
              display: "flex", justifyContent: "center",
            }}>
              <div style={{ width: "100%", maxWidth: 720 }}>
                <TranscriptView
                  messages={TRANSCRIPT}
                  onSelectArtifact={handleSelectArtifact}
                  selectedArtifactId={detailId}
                  isMobile={false}
                />
                {on && (
                  <div style={{ padding: "16px 0", display: "flex", alignItems: "center", gap: 8 }}>
                    <VoiceDot state={voiceState} size={7} />
                    <span style={{ fontSize: 14, color: C.textSec }}>{tx ? "Gemini is speaking..." : "Listening..."}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Input */}
            <div style={{
              borderTop: `1px solid ${C.border}`, padding: "10px 32px",
              display: "flex", justifyContent: "center", backgroundColor: C.bg, flexShrink: 0,
            }}>
              <div style={{
                width: "100%", maxWidth: 720, display: "flex", alignItems: "center",
                border: `1px solid ${C.border}`, borderRadius: 12,
                padding: "0 16px", height: 44, backgroundColor: C.surface,
              }}>
                <span style={{ color: C.textTer, fontSize: 14, marginRight: 10, fontFamily: mono }}>{"\u276F"}</span>
                <input
                  value={inp} onChange={e => setInp(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && inp.trim()) setInp(""); }}
                  placeholder={on ? "Voice active \u2014 or type here" : "Type a message..."}
                  style={{ flex: 1, backgroundColor: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14, fontFamily: sans }}
                />
              </div>
            </div>
          </div>

          {/* Detail panel */}
          {hasDetail && (
            <div style={{
              width: 420, flexShrink: 0, borderLeft: `1px solid ${C.border}`,
              backgroundColor: C.bg, display: "flex", flexDirection: "column",
            }}>
              <DetailPanel artifact={detailArtifact} onClose={() => { setDetailArtifact(null); setDetailId(null); }} />
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes vcc-ring { 0%{transform:scale(1);opacity:.35} 100%{transform:scale(1.8);opacity:0} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::placeholder { color: ${C.textFaint}; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
      `}</style>
    </div>
  );
}
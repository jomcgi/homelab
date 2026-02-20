import { GitPullRequest } from "lucide-react";
import { C, sans, mono } from "../tokens.js";

function prColor(state) {
  switch (state) {
    case "merged": return C.prMerged;
    case "closed": return C.prClosed;
    default: return C.prOpen;
  }
}

function prBgColor(state) {
  switch (state) {
    case "merged": return C.prMergedBg;
    case "closed": return C.prClosedBg;
    default: return C.prOpenBg;
  }
}

function PRPill({ pr, compact }) {
  const color = prColor(pr.state);
  const bg = prBgColor(pr.state);
  const title = pr.title || `PR #${pr.pr_number}`;
  const maxLen = compact ? 30 : 50;
  const truncated = title.length > maxLen ? title.slice(0, maxLen - 1) + "\u2026" : title;

  return (
    <button
      onClick={() => window.open(pr.url, "_blank")}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        padding: "3px 10px 3px 7px", borderRadius: 16,
        border: "none", cursor: "pointer",
        backgroundColor: bg, fontFamily: sans, fontSize: 12,
        color: color, fontWeight: 500, whiteSpace: "nowrap",
        transition: "opacity 150ms",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.8"; }}
      onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
      title={`${pr.repo}#${pr.pr_number}: ${pr.title || ""} (${pr.state})`}
    >
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        backgroundColor: color, flexShrink: 0,
      }} />
      <GitPullRequest size={12} />
      <span style={{ fontFamily: mono }}>#{pr.pr_number}</span>
      <span style={{ color: C.textSec, fontWeight: 400, overflow: "hidden", textOverflow: "ellipsis" }}>
        {truncated}
      </span>
    </button>
  );
}

export function PRBar({ prs }) {
  if (!prs || prs.length === 0) return null;

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "4px 20px", height: 36, flexShrink: 0,
      borderBottom: `1px solid ${C.border}`,
      backgroundColor: C.bgSub,
      overflowX: "auto", overflowY: "hidden",
    }}>
      <GitPullRequest size={14} color={C.textTer} style={{ flexShrink: 0 }} />
      {prs.map((pr) => (
        <PRPill key={`${pr.repo}-${pr.pr_number}`} pr={pr} compact />
      ))}
    </div>
  );
}

export function InlinePRPill({ pr }) {
  return <PRPill pr={pr} compact={false} />;
}

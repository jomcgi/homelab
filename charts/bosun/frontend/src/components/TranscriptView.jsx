import { useState } from "react";
import {
  Mic,
  ChevronUp,
  ChevronRight,
  ChevronDown,
  Check,
  AlertTriangle,
  XCircle,
  Volume2,
  Zap,
} from "lucide-react";
import { C, sans, mono } from "../tokens.js";
import { MarkdownContent } from "./MarkdownContent.jsx";
import { InlineArtifact } from "./InlineArtifact.jsx";
import { ArtifactCard } from "./ArtifactCard.jsx";
import { ActionChips } from "./ActionChips.jsx";
import { CopyButton } from "./CopyButton.jsx";
import { InlinePRPill } from "./PRBar.jsx";

// ── Message grouping ───────────────────────────────────────────────────────
function useGroups(messages) {
  const groups = [];
  let cur = null;
  messages.forEach((m) => {
    if (m.role === "voice") {
      if (cur) groups.push(cur);
      cur = {
        voice: m,
        steps: [],
        result: null,
        summary: null,
        approval: null,
      };
    } else if (m.role === "claude") {
      if (!cur)
        cur = {
          voice: null,
          steps: [],
          result: null,
          summary: null,
          approval: null,
        };
      if (m.status === "thinking" || m.status === "tool") cur.steps.push(m);
      else if (m.status === "approval") cur.approval = m;
      else if (m.status === "done") cur.result = m;
    } else if (m.role === "gemini") {
      if (cur) {
        cur.summary = m;
        groups.push(cur);
        cur = null;
      }
    }
  });
  if (cur) groups.push(cur);
  return groups;
}

function stepSummary(steps) {
  const tools = [
    ...new Set(
      steps
        .map((s) => {
          const m = s.text?.match(/^(\w+)[\s:(]/);
          return m ? m[1] : null;
        })
        .filter(Boolean),
    ),
  ];
  const shown = tools.slice(0, 3);
  const extra = tools.length - shown.length;
  const label = shown.join(" \u2192 ");
  return `${steps.length} step${steps.length > 1 ? "s" : ""} \u2014 ${label}${extra > 0 ? ` +${extra} more` : ""}`;
}

export function TranscriptView({
  messages,
  onSelectArtifact,
  selectedArtifactId,
  isMobile,
  onApprove,
  onReject,
  actions,
  onAction,
}) {
  const groups = useGroups(messages);
  const [expandedSteps, setExpandedSteps] = useState({});
  const [expandedErrors, setExpandedErrors] = useState({});

  return (
    <div data-testid="transcript">
      {groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 28 }}>
          {/* Voice input */}
          {g.voice && (
            <div
              style={{
                padding: "12px 16px",
                marginBottom: 10,
                backgroundColor: g.voice._queued ? C.surface : C.youBg,
                borderRadius: 12,
                borderLeft: `3px solid ${g.voice._queued ? C.textTer : C.you}`,
                opacity: g.voice._queued ? 0.75 : 1,
                transition: "all 300ms",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 5,
                }}
              >
                <Mic size={13} color={g.voice._queued ? C.textTer : C.you} />
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: g.voice._queued ? C.textTer : C.you,
                  }}
                >
                  You
                </span>
                <span style={{ fontSize: 12, color: C.textTer }}>
                  {g.voice.time}
                </span>
                {g.voice._queued && (
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: C.textTer,
                      backgroundColor: C.surfaceHover,
                      padding: "1px 6px",
                      borderRadius: 4,
                      letterSpacing: 0.3,
                    }}
                  >
                    QUEUED
                  </span>
                )}
              </div>
              <div
                style={{
                  fontSize: 15,
                  color: g.voice._queued ? C.textSec : C.text,
                  lineHeight: 1.55,
                }}
              >
                {g.voice.text}
              </div>
            </div>
          )}

          {/* Intermediate steps */}
          {g.steps.length > 0 &&
            (() => {
              const errorSteps = g.steps.filter((s) => s._error);
              const normalSteps = g.steps.filter((s) => !s._error);
              return (
                <div style={{ margin: "4px 0 8px" }}>
                  {/* Normal steps — collapsible */}
                  {normalSteps.length > 0 && (
                    <>
                      <button
                        onClick={() =>
                          setExpandedSteps((p) => ({ ...p, [gi]: !p[gi] }))
                        }
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          padding: "6px 10px",
                          borderRadius: 8,
                          background: "none",
                          border: "1px solid transparent",
                          borderLeft: expandedSteps[gi]
                            ? `2px solid ${C.stepBorder}`
                            : "2px solid transparent",
                          cursor: "pointer",
                          fontFamily: mono,
                          fontSize: 12,
                          color: C.stepText,
                        }}
                      >
                        {expandedSteps[gi] ? (
                          <ChevronUp size={13} />
                        ) : (
                          <ChevronRight size={13} />
                        )}
                        <Zap size={12} />
                        <span style={{ fontWeight: 500 }}>
                          {stepSummary(normalSteps)}
                        </span>
                      </button>
                      {expandedSteps[gi] && (
                        <div
                          style={{
                            marginTop: 4,
                            padding: "8px 0 4px 12px",
                            borderLeft: `2px solid ${C.border}`,
                            marginLeft: 16,
                          }}
                        >
                          {normalSteps.map((s, si) => (
                            <div
                              key={si}
                              style={{
                                padding: "5px 10px",
                                marginBottom: 3,
                                borderRadius: 6,
                                fontSize: 13,
                                fontFamily: mono,
                                color: C.textSec,
                                lineHeight: 1.5,
                                backgroundColor:
                                  s.status === "thinking"
                                    ? C.surface
                                    : "transparent",
                                wordBreak: "break-word",
                              }}
                            >
                              {s.text}
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  {/* Error steps — always visible inline */}
                  {errorSteps.map((s) => {
                    const errKey = `${gi}-${s.id}`;
                    const isOpen = expandedErrors[errKey];
                    return (
                      <div
                        key={s.id}
                        style={{
                          margin: "6px 0",
                          borderRadius: 8,
                          border: `1px solid ${C.danger}22`,
                          backgroundColor: `${C.danger}08`,
                        }}
                      >
                        <button
                          onClick={() =>
                            setExpandedErrors((p) => ({
                              ...p,
                              [errKey]: !p[errKey],
                            }))
                          }
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            width: "100%",
                            padding: "8px 12px",
                            borderRadius: 8,
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            fontFamily: sans,
                            fontSize: 12,
                            color: C.danger,
                            textAlign: "left",
                          }}
                        >
                          <XCircle size={14} style={{ flexShrink: 0 }} />
                          <span style={{ flex: 1, fontWeight: 500 }}>
                            {s.text}
                          </span>
                          {isOpen ? (
                            <ChevronUp size={13} />
                          ) : (
                            <ChevronDown size={13} />
                          )}
                        </button>
                        {isOpen && (
                          <pre
                            style={{
                              margin: "0 12px 10px",
                              padding: "10px 12px",
                              backgroundColor: C.surface,
                              borderRadius: 6,
                              fontSize: 11,
                              fontFamily: mono,
                              color: C.textSec,
                              lineHeight: 1.5,
                              overflow: "auto",
                              maxHeight: 300,
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {s._errorDetail}
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })()}

          {/* Approval */}
          {g.approval && (
            <div
              style={{
                margin: "8px 0",
                padding: "12px 16px",
                backgroundColor: C.approvalBg,
                border: `1px solid ${C.approvalBorder}`,
                borderRadius: 10,
                display: "flex",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <AlertTriangle
                size={16}
                color={C.approval}
                style={{ flexShrink: 0 }}
              />
              <span
                style={{
                  fontFamily: mono,
                  fontSize: 13,
                  color: C.text,
                  flex: 1,
                  minWidth: 160,
                }}
              >
                {g.approval.text}
              </span>
              {g.approval._approvalId && (
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => onApprove(g.approval._approvalId)}
                    style={{
                      padding: "7px 20px",
                      borderRadius: 7,
                      border: "none",
                      cursor: "pointer",
                      backgroundColor: C.text,
                      color: C.bg,
                      fontFamily: sans,
                      fontSize: 13,
                      fontWeight: 500,
                    }}
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => onReject(g.approval._approvalId)}
                    style={{
                      padding: "7px 20px",
                      borderRadius: 7,
                      cursor: "pointer",
                      backgroundColor: "transparent",
                      color: C.textSec,
                      border: `1px solid ${C.border}`,
                      fontFamily: sans,
                      fontSize: 13,
                    }}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Claude Code result */}
          {g.result && (
            <div style={{ marginBottom: 10 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 4,
                }}
              >
                <Check size={13} color={C.success} />
                <span
                  style={{ fontSize: 12, fontWeight: 600, color: C.textSec }}
                >
                  Claude Code
                </span>
                <span style={{ fontSize: 12, color: C.textTer }}>
                  {g.result.time}
                </span>
              </div>
              <div
                className="vcc-copy-trigger"
                style={{ position: "relative" }}
              >
                {!g.result._streaming && g.result.text && (
                  <CopyButton getText={() => g.result.text} />
                )}
                {g.result._streaming ? (
                  <div
                    style={{
                      fontSize: 14,
                      color: C.textSec,
                      lineHeight: 1.55,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {g.result.text}
                  </div>
                ) : (
                  <MarkdownContent text={g.result.text} />
                )}
              </div>

              {isMobile ? (
                <>
                  {g.result.artifact && (
                    <InlineArtifact artifact={g.result.artifact} />
                  )}
                  {g.result.artifact2 && (
                    <InlineArtifact artifact={g.result.artifact2} />
                  )}
                </>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 0 }}>
                  {g.result.artifact &&
                    (g.result.artifact.type === "image" ||
                    g.result.artifact.type === "mermaid" ? (
                      <InlineArtifact
                        artifact={g.result.artifact}
                        onOpen={(a) => onSelectArtifact(a, g.result.id + "-1")}
                      />
                    ) : (
                      <ArtifactCard
                        artifact={g.result.artifact}
                        selected={selectedArtifactId === g.result.id + "-1"}
                        onClick={() =>
                          onSelectArtifact(
                            g.result.artifact,
                            g.result.id + "-1",
                          )
                        }
                      />
                    ))}
                  {g.result.artifact2 &&
                    (g.result.artifact2.type === "image" ||
                    g.result.artifact2.type === "mermaid" ? (
                      <InlineArtifact
                        artifact={g.result.artifact2}
                        onOpen={(a) => onSelectArtifact(a, g.result.id + "-2")}
                      />
                    ) : (
                      <ArtifactCard
                        artifact={g.result.artifact2}
                        selected={selectedArtifactId === g.result.id + "-2"}
                        onClick={() =>
                          onSelectArtifact(
                            g.result.artifact2,
                            g.result.id + "-2",
                          )
                        }
                      />
                    ))}
                </div>
              )}

              {g.result._prs?.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                    marginTop: 8,
                  }}
                >
                  {g.result._prs.map((pr) => (
                    <InlinePRPill key={`${pr.repo}-${pr.pr_number}`} pr={pr} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Voice summary + action chips */}
          {g.summary && (
            <div
              style={{
                padding: "10px 14px",
                backgroundColor: C.voiceBg,
                borderRadius: 10,
                borderLeft: `2px solid ${C.voiceBorder}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 5,
                }}
              >
                <Volume2 size={13} color={C.voice} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.voice }}>
                  Spoken
                </span>
                <span style={{ fontSize: 12, color: C.textTer }}>
                  {g.summary.time}
                </span>
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: C.text,
                  lineHeight: 1.55,
                  fontStyle: "italic",
                }}
              >
                {g.summary.text}
              </div>
              {/* Show action chips after the last summary */}
              {gi === groups.length - 1 && actions?.length > 0 && (
                <ActionChips actions={actions} onAction={onAction} />
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import {
  listJobs,
  listAgents,
  submitPipeline,
  cancelJob,
  submitJob,
  getJob,
} from "./api.js";
import PipelineComposer from "./PipelineComposer.jsx";
import { CONDITION_STYLES } from "./pipeline-config.js";

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL = 5000;

const STATUS_META = {
  PENDING: { color: "#f59e0b", label: "pending" },
  RUNNING: { color: "#3b82f6", label: "running" },
  SUCCEEDED: { color: "#22c55e", label: "done" },
  FAILED: { color: "#ef4444", label: "failed" },
  CANCELLED: { color: "#d1d5db", label: "cancelled" },
  BLOCKED: { color: "#9ca3af", label: "blocked" },
  SKIPPED: { color: "#d1d5db", label: "skipped" },
};

// ─── Utils ────────────────────────────────────────────────────────────────────

function timeAgo(ts) {
  if (!ts) return "";
  const s = Math.floor((Date.now() - new Date(ts)) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function elapsed(start, end) {
  if (!start) return "";
  const s = Math.floor((new Date(end || Date.now()) - new Date(start)) / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Extract the structured result from the latest attempt. */
function getResult(job) {
  if (!job.attempts?.length) return null;
  return job.attempts[job.attempts.length - 1].result || null;
}

/** Resolve agent metadata, falling back to a neutral default. */
function resolveAgent(agentId, agents) {
  return (
    agents.find((a) => a.id === agentId) || {
      id: agentId,
      label: agentId,
      icon: "◆",
      bg: "#f3f4f6",
      fg: "#6b7280",
    }
  );
}

/** Group jobs by pipeline_id. Non-pipeline jobs get their own group. */
function groupJobs(jobs) {
  const pipelines = new Map();
  const singles = [];

  for (const job of jobs) {
    if (job.pipeline_id) {
      if (!pipelines.has(job.pipeline_id)) {
        pipelines.set(job.pipeline_id, []);
      }
      pipelines.get(job.pipeline_id).push(job);
    } else {
      singles.push({ type: "single", job });
    }
  }

  const groups = [];
  for (const [pipelineId, pipelineJobs] of pipelines) {
    // Sort by step_index
    pipelineJobs.sort((a, b) => a.step_index - b.step_index);
    groups.push({ type: "pipeline", pipelineId, jobs: pipelineJobs });
  }

  // Add singles
  groups.push(...singles);

  // Sort groups by most recent activity (first job's updated_at)
  groups.sort((a, b) => {
    const aTime =
      a.type === "pipeline" ? a.jobs[0].updated_at : a.job.updated_at;
    const bTime =
      b.type === "pipeline" ? b.jobs[0].updated_at : b.job.updated_at;
    return new Date(bTime) - new Date(aTime);
  });

  return groups;
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function GitHubIcon({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function ChevronDown({ size = 12, open }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      style={{
        transform: open ? "rotate(180deg)" : "rotate(0deg)",
        transition: "transform 0.15s ease",
      }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

// ─── Dot ──────────────────────────────────────────────────────────────────────

function Dot({ status }) {
  const { color } = STATUS_META[status] ?? STATUS_META.PENDING;
  const pulse = status === "RUNNING";
  return (
    <span
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        width: 7,
        height: 7,
      }}
    >
      {pulse && (
        <span
          style={{
            position: "absolute",
            display: "inline-flex",
            width: "100%",
            height: "100%",
            borderRadius: "50%",
            background: color,
            opacity: 0.5,
            animation: "ping 1s cubic-bezier(0,0,0.2,1) infinite",
          }}
        />
      )}
      <span
        style={{
          display: "block",
          borderRadius: "50%",
          width: 7,
          height: 7,
          background: color,
        }}
      />
    </span>
  );
}

// ─── GitHub pill ──────────────────────────────────────────────────────────────

function ResultPill({ result }) {
  if (!result) return null;
  const label =
    result.type === "pr" ? "PR" : result.type === "issue" ? "Issue" : "Gist";
  return (
    <a
      href={result.url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        color: "#6b7280",
        border: "1px solid #e5e7eb",
        borderRadius: 4,
        padding: "1px 6px",
        textDecoration: "none",
        flexShrink: 0,
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.color = "#1f2937")}
      onMouseLeave={(e) => (e.currentTarget.style.color = "#6b7280")}
    >
      <GitHubIcon size={10} />
      {label}
    </a>
  );
}

// ─── Pipeline flow (compact, inline) ─────────────────────────────────────────

function PipelineFlow({ steps, jobs, agents }) {
  // Use real jobs if available, otherwise fall back to parsed steps
  const items = jobs
    ? jobs.map((j) => ({
        agent: j.profile,
        task: j.title || j.task,
        condition: j.step_condition || "always",
        status: j.status,
      }))
    : steps.map((s) => ({
        agent: s.agent,
        task: s.task,
        condition: s.condition || "always",
        status: null,
      }));

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        overflow: "hidden",
        minWidth: 0,
      }}
    >
      {items.map((item, i) => {
        const ag = resolveAgent(item.agent, agents);
        const cond = i > 0 ? item.condition : null;
        const condStyle = cond
          ? CONDITION_STYLES[cond] || CONDITION_STYLES["always"]
          : null;
        const isSkipped =
          item.status === "SKIPPED" || item.status === "CANCELLED";
        const isBlocked = item.status === "BLOCKED";
        const isFailed = item.status === "FAILED";

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 0,
              minWidth: 0,
              flexShrink: i === items.length - 1 ? 1 : 0,
            }}
          >
            {/* Connector */}
            {i > 0 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0,
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: 12,
                    height: 1,
                    background: isFailed
                      ? "#ef4444"
                      : condStyle?.border || "#e5e7eb",
                  }}
                />
                {cond !== "always" && (
                  <div
                    title={cond}
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: condStyle?.border || "#e5e7eb",
                      flexShrink: 0,
                    }}
                  />
                )}
                <div
                  style={{
                    width: 8,
                    height: 1,
                    background: isFailed
                      ? "#ef4444"
                      : condStyle?.border || "#e5e7eb",
                  }}
                />
              </div>
            )}
            {/* Agent pill with status dot */}
            <div
              title={`${ag.label}: ${item.task}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "3px 8px 3px 5px",
                borderRadius: 6,
                background: isSkipped
                  ? "transparent"
                  : isBlocked
                    ? "#f9fafb"
                    : ag.bg,
                border: isSkipped
                  ? "1px dashed #d1d5db"
                  : isBlocked
                    ? "1px solid #e5e7eb"
                    : "none",
                opacity: isSkipped || isBlocked ? 0.6 : 1,
                flexShrink: 0,
                maxWidth: 120,
              }}
            >
              {item.status && <Dot status={item.status} />}
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  color: isSkipped ? "#9ca3af" : ag.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  textDecoration: isSkipped ? "line-through" : "none",
                }}
              >
                {ag.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Pipeline detail (expanded view) ─────────────────────────────────────────

function PipelineDetail({ steps, jobs, agents }) {
  const [openStep, setOpenStep] = useState(null);
  const [outputOpen, setOutputOpen] = useState(false);

  const items = jobs
    ? jobs.map((j) => ({
        agent: j.profile,
        task: j.task,
        title: j.title,
        condition: j.step_condition || "always",
        status: j.status,
        summary: j.summary,
        attempts: j.attempts,
        failure_summary: j.failure_summary,
      }))
    : steps.map((s) => ({
        agent: s.agent,
        task: s.task,
        title: null,
        condition: s.condition || "always",
        status: null,
        summary: null,
        attempts: null,
        failure_summary: null,
      }));

  return (
    <div
      style={{
        padding: "12px 20px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 0,
      }}
    >
      {items.map((item, i) => {
        const ag = resolveAgent(item.agent, agents);
        const cond = item.condition;
        const condStyle = CONDITION_STYLES[cond] || CONDITION_STYLES["always"];
        const isSkipped =
          item.status === "SKIPPED" || item.status === "CANCELLED";
        const isOpen = openStep === i;
        const hasStatus = !!item.status;
        const result = getResult({ attempts: item.attempts });
        const attempt = item.attempts?.[item.attempts.length - 1];
        const stepSummary = result?.summary || item.failure_summary;
        const hasOutput =
          attempt?.output ||
          item.status === "PENDING" ||
          item.status === "RUNNING";

        return (
          <div key={i}>
            {/* Vertical connector */}
            {i > 0 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  paddingLeft: 14,
                }}
              >
                <div
                  style={{
                    width: 1,
                    height: 20,
                    background: condStyle.border || "#e5e7eb",
                    flexShrink: 0,
                  }}
                />
                {cond !== "always" && (
                  <span
                    style={{
                      fontSize: 9,
                      fontWeight: 500,
                      color: condStyle.color,
                      padding: "1px 6px",
                      borderRadius: 8,
                      border: `1px solid ${condStyle.border}`,
                      background: condStyle.bg,
                      lineHeight: 1.4,
                    }}
                  >
                    {cond}
                  </span>
                )}
              </div>
            )}
            {/* Step card */}
            <div
              onClick={() => {
                if (hasStatus) {
                  if (isOpen) {
                    setOpenStep(null);
                  } else {
                    setOpenStep(i);
                    setOutputOpen(false);
                  }
                }
              }}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "8px 12px",
                background: isSkipped
                  ? "transparent"
                  : isOpen
                    ? "#f3f4f6"
                    : "#fafafa",
                borderRadius: isOpen ? "8px 8px 0 0" : 8,
                border: isSkipped ? "1px dashed #e5e7eb" : "1px solid #f0f0f0",
                opacity: isSkipped ? 0.5 : 1,
                cursor: hasStatus ? "pointer" : "default",
                transition: "background 0.15s",
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  background: ag.bg,
                  color: ag.fg,
                  flexShrink: 0,
                  marginTop: 1,
                }}
              >
                {ag.icon}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    marginBottom: 2,
                  }}
                >
                  {item.status && <Dot status={item.status} />}
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: "#374151",
                      textDecoration: isSkipped ? "line-through" : "none",
                    }}
                  >
                    {item.title || ag.label}
                  </span>
                  {isSkipped && (
                    <span
                      style={{
                        fontSize: 10,
                        color: "#9ca3af",
                        fontStyle: "italic",
                      }}
                    >
                      {item.status === "SKIPPED" ? "Skipped" : "Cancelled"}
                    </span>
                  )}
                  <ResultPill result={result} />
                </div>
                <div
                  style={{ fontSize: 11.5, color: "#9ca3af", lineHeight: 1.5 }}
                >
                  {item.summary || item.task || "(no task)"}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  flexShrink: 0,
                  marginTop: 2,
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    color: "#d1d5db",
                    fontFamily: "monospace",
                  }}
                >
                  {i + 1}
                </span>
                {hasStatus && <ChevronDown size={10} open={isOpen} />}
              </div>
            </div>

            {/* Expanded step content */}
            {isOpen && (
              <div
                style={{
                  border: "1px solid #f0f0f0",
                  borderTop: "none",
                  borderRadius: "0 0 8px 8px",
                  overflow: "hidden",
                }}
              >
                {stepSummary && (
                  <p
                    style={{
                      padding: "8px 12px",
                      fontSize: 11.5,
                      color: item.failure_summary ? "#f87171" : "#6b7280",
                      lineHeight: 1.5,
                      margin: 0,
                    }}
                  >
                    {stepSummary}
                  </p>
                )}

                {hasOutput && (
                  <>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setOutputOpen((o) => !o);
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        width: "100%",
                        padding: "6px 12px",
                        fontSize: 11,
                        color: "#9ca3af",
                        background: outputOpen ? "#f9fafb" : "transparent",
                        border: "none",
                        borderTop: stepSummary ? "1px solid #f3f4f6" : "none",
                        cursor: "pointer",
                        outline: "none",
                        fontFamily: "inherit",
                        transition: "color 0.15s",
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.color = "#374151")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.color = "#9ca3af")
                      }
                    >
                      <ChevronDown size={10} open={outputOpen} />
                      Output
                      {attempt?.exit_code != null && (
                        <span
                          style={{
                            fontFamily: "monospace",
                            color:
                              attempt.exit_code === 0 ? "#22c55e" : "#f87171",
                          }}
                        >
                          exit {attempt.exit_code}
                        </span>
                      )}
                      {item.status === "RUNNING" && (
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                            color: "#60a5fa",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-flex",
                              width: 5,
                              height: 5,
                              borderRadius: "50%",
                              background: "#60a5fa",
                              animation:
                                "ping 1s cubic-bezier(0,0,0.2,1) infinite",
                            }}
                          />
                          live
                        </span>
                      )}
                      {attempt?.started_at && (
                        <span
                          style={{
                            marginLeft: "auto",
                            fontFamily: "monospace",
                            color: "#d1d5db",
                          }}
                        >
                          {elapsed(attempt.started_at, attempt.finished_at)}
                        </span>
                      )}
                    </button>

                    {outputOpen && (
                      <pre
                        style={{
                          padding: "12px",
                          fontSize: 11,
                          fontFamily: "monospace",
                          lineHeight: 1.6,
                          color: "#374151",
                          whiteSpace: "pre-wrap",
                          overflow: "auto",
                          maxHeight: 200,
                          margin: 0,
                          borderTop: "1px solid #f3f4f6",
                        }}
                      >
                        {attempt?.output || (
                          <span
                            style={{ color: "#d1d5db", fontStyle: "italic" }}
                          >
                            {item.status === "PENDING" ||
                            item.status === "RUNNING"
                              ? "Waiting for output..."
                              : "No output"}
                          </span>
                        )}
                      </pre>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Job row ──────────────────────────────────────────────────────────────────

function JobRow({ job, agents, onCancel, onApplyPipeline, isMobile }) {
  const [open, setOpen] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const canCancel = job.status === "PENDING" || job.status === "RUNNING";
  const result = getResult(job);
  const attempt = job.attempts?.[job.attempts.length - 1];
  const summary = result?.summary || job.failure_summary;
  const hasOutput = attempt?.output || job.status === "PENDING";
  const isExpandable = summary || hasOutput;

  return (
    <div
      style={{
        borderBottom: "1px solid #f3f4f6",
        transition: "background 0.15s",
        background: open ? "rgba(249,250,251,0.6)" : "transparent",
      }}
    >
      {/* Main row */}
      <div
        onClick={isExpandable ? () => setOpen((o) => !o) : undefined}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 4px",
          cursor: isExpandable ? "pointer" : "default",
        }}
      >
        <Dot status={job.status} />

        {/* Task title */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: 13,
              color: "#374151",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              margin: 0,
            }}
          >
            {job.title || job.task}
          </p>
        </div>

        {/* Right-side metadata */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <ResultPill result={result} />

          {onApplyPipeline &&
            result?.pipeline?.length > 0 &&
            job.status === "SUCCEEDED" && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onApplyPipeline(result.pipeline, result.url);
                }}
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  padding: "2px 8px",
                  background: "#4f46e5",
                  color: "#fff",
                  borderRadius: 4,
                  border: "none",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  flexShrink: 0,
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "#4338ca")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "#4f46e5")
                }
              >
                Apply pipeline
              </button>
            )}

          {job.profile && !isMobile && (
            <span
              style={{
                fontSize: 11,
                fontFamily: "monospace",
                color: "#d1d5db",
              }}
            >
              {job.profile}
            </span>
          )}

          <span
            style={{
              fontSize: 11,
              color: "#d1d5db",
              fontVariantNumeric: "tabular-nums",
              width: 24,
              textAlign: "right",
            }}
          >
            {timeAgo(job.updated_at)}
          </span>

          {isExpandable && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setOpen((o) => !o);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
                color: "#9ca3af",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: "0 0 0 4px",
                outline: "none",
                transition: "color 0.15s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "#374151")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "#9ca3af")}
            >
              <ChevronDown size={11} open={open} />
            </button>
          )}

          {canCancel && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onCancel(job.id);
              }}
              style={{
                fontSize: 11,
                color: "#f87171",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 0,
                outline: "none",
                transition: "color 0.15s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "#dc2626")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "#f87171")}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Expanded content */}
      {open && (
        <div style={{ borderTop: "1px solid #f3f4f6" }}>
          {summary && (
            <p
              style={{
                padding: "10px 20px",
                fontSize: 12,
                color: job.failure_summary ? "#f87171" : "#6b7280",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {summary}
            </p>
          )}

          {/* Output toggle */}
          {hasOutput && (
            <>
              <button
                onClick={() => setOutputOpen((o) => !o)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  width: "100%",
                  padding: "8px 20px",
                  fontSize: 11,
                  color: "#9ca3af",
                  background: outputOpen ? "#f9fafb" : "transparent",
                  border: "none",
                  borderTop: summary ? "1px solid #f3f4f6" : "none",
                  cursor: "pointer",
                  outline: "none",
                  transition: "color 0.15s, background 0.15s",
                  fontFamily: "inherit",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#374151")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#9ca3af")}
              >
                <ChevronDown size={10} open={outputOpen} />
                Output
                {attempt?.exit_code != null && (
                  <span
                    style={{
                      fontFamily: "monospace",
                      color: attempt.exit_code === 0 ? "#22c55e" : "#f87171",
                    }}
                  >
                    exit {attempt.exit_code}
                  </span>
                )}
                {job.status === "RUNNING" && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      color: "#60a5fa",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-flex",
                        width: 5,
                        height: 5,
                        borderRadius: "50%",
                        background: "#60a5fa",
                        animation: "ping 1s cubic-bezier(0,0,0.2,1) infinite",
                      }}
                    />
                    live
                  </span>
                )}
                {attempt?.started_at && (
                  <span
                    style={{
                      marginLeft: "auto",
                      fontFamily: "monospace",
                      color: "#d1d5db",
                    }}
                  >
                    {elapsed(attempt.started_at, attempt.finished_at)}
                  </span>
                )}
              </button>

              {outputOpen && (
                <pre
                  style={{
                    padding: "16px 20px",
                    fontSize: 12,
                    fontFamily: "monospace",
                    lineHeight: 1.6,
                    color: "#374151",
                    whiteSpace: "pre-wrap",
                    overflow: "auto",
                    maxHeight: 260,
                    margin: 0,
                    borderTop: "1px solid #f3f4f6",
                  }}
                >
                  {attempt?.output ||
                    (job.status === "PENDING" ? (
                      <span
                        style={{
                          color: "#d1d5db",
                          fontStyle: "italic",
                        }}
                      >
                        Waiting for sandbox...
                      </span>
                    ) : (
                      <span
                        style={{
                          color: "#d1d5db",
                          fontStyle: "italic",
                        }}
                      >
                        No output
                      </span>
                    ))}
                </pre>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Pipeline row (group of pipeline jobs) ───────────────────────────────────

function PipelineRow({ pipelineJobs, agents, onCancel, isMobile }) {
  const [open, setOpen] = useState(false);
  const firstJob = pipelineJobs[0];
  const pipelineSummary = firstJob.pipeline_summary;
  const hasRunning = pipelineJobs.some((j) => j.status === "RUNNING");
  const hasFailed = pipelineJobs.some((j) => j.status === "FAILED");
  const allDone = pipelineJobs.every((j) =>
    ["SUCCEEDED", "FAILED", "CANCELLED", "SKIPPED"].includes(j.status),
  );

  // Overall pipeline status
  const overallStatus = hasRunning
    ? "RUNNING"
    : hasFailed
      ? "FAILED"
      : allDone
        ? pipelineJobs.every((j) => j.status === "SUCCEEDED")
          ? "SUCCEEDED"
          : "FAILED"
        : "PENDING";

  const canCancel = pipelineJobs.some(
    (j) =>
      j.status === "PENDING" ||
      j.status === "RUNNING" ||
      j.status === "BLOCKED",
  );

  return (
    <div
      style={{
        borderBottom: "1px solid #f3f4f6",
        transition: "background 0.15s",
        background: open ? "rgba(249,250,251,0.6)" : "transparent",
      }}
    >
      {/* Compact row */}
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 4px",
          cursor: "pointer",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          {pipelineSummary && (
            <p
              style={{
                fontSize: 12,
                color: "#6b7280",
                margin: "0 0 4px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {pipelineSummary}
            </p>
          )}
          <PipelineFlow jobs={pipelineJobs} agents={agents} />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "#d1d5db",
              fontVariantNumeric: "tabular-nums",
              width: 24,
              textAlign: "right",
            }}
          >
            {timeAgo(firstJob.updated_at)}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              fontSize: 11,
              color: "#9ca3af",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "0 0 0 4px",
              outline: "none",
            }}
          >
            <ChevronDown size={11} open={open} />
          </button>
          {canCancel && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                // Cancel the first non-terminal job
                const active = pipelineJobs.find((j) =>
                  ["PENDING", "RUNNING", "BLOCKED"].includes(j.status),
                );
                if (active) onCancel(active.id);
              }}
              style={{
                fontSize: 11,
                color: "#f87171",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 0,
                outline: "none",
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Expanded: per-step detail */}
      {open && (
        <div style={{ borderTop: "1px solid #f3f4f6" }}>
          <PipelineDetail jobs={pipelineJobs} agents={agents} />
        </div>
      )}
    </div>
  );
}

// ─── Job list with filter + search ───────────────────────────────────────────

function JobList({ jobs, agents, onCancel, onApplyPipeline, isMobile }) {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  // Filter jobs first, then group
  const filtered = jobs.filter((j) => {
    const matchStatus = status === "all" || j.status === status;
    const matchSearch =
      !search ||
      (j.task || "").toLowerCase().includes(search.toLowerCase()) ||
      (j.title || "").toLowerCase().includes(search.toLowerCase());
    return matchStatus && matchSearch;
  });

  const groups = groupJobs(filtered);

  return (
    <div>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 8,
          padding: "0 4px",
        }}
      >
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          style={{
            fontSize: 11,
            color: "#9ca3af",
            background: "transparent",
            border: "none",
            outline: "none",
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          <option value="all">All</option>
          <option value="RUNNING">Running</option>
          <option value="PENDING">Pending</option>
          <option value="BLOCKED">Blocked</option>
          <option value="SUCCEEDED">Done</option>
          <option value="FAILED">Failed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          placeholder="Search..."
          style={{
            marginLeft: "auto",
            fontSize: 11,
            color: "#6b7280",
            background: "transparent",
            border: "none",
            outline: "none",
            width: searchFocused ? 192 : 112,
            transition: "width 0.2s ease",
            textAlign: "right",
            fontFamily: "inherit",
          }}
        />
      </div>

      {/* Grouped list */}
      <div>
        {groups.length === 0 ? (
          <p style={{ fontSize: 12, color: "#d1d5db", padding: "16px 4px" }}>
            No jobs match
          </p>
        ) : (
          groups.map((group) =>
            group.type === "pipeline" ? (
              <PipelineRow
                key={group.pipelineId}
                pipelineJobs={group.jobs}
                agents={agents}
                onCancel={onCancel}
                isMobile={isMobile}
              />
            ) : (
              <JobRow
                key={group.job.id}
                job={group.job}
                agents={agents}
                onCancel={onCancel}
                onApplyPipeline={onApplyPipeline}
                isMobile={isMobile}
              />
            ),
          )
        )}
      </div>
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [agents, setAgents] = useState([]);
  const [toast, setToast] = useState(null);
  const [windowWidth, setWindowWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1024,
  );
  const isMobile = windowWidth < 640;

  // Deep Plan state
  const [deepPlanJobId, setDeepPlanJobId] = useState(null);
  const [deepPlanStatus, setDeepPlanStatus] = useState(null); // null | "running" | "done" | "failed"
  const [analysisUrl, setAnalysisUrl] = useState(null);
  const [deepPlanResult, setDeepPlanResult] = useState(null);

  const notify = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  // Fetch agent registry on mount
  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents || []);
      })
      .catch(() => {
        setAgents([]);
      });
  }, []);

  // Track window width
  useEffect(() => {
    const onResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Fetch jobs with polling
  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs({ limit: 50 });
      setJobs(data.jobs || []);
    } catch {
      // Silently retry on next poll
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const id = setInterval(fetchJobs, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchJobs]);

  const handlePipelineSubmit = useCallback(
    async (spec) => {
      try {
        await submitPipeline(spec);
        notify(`Pipeline submitted (${spec.steps.length} steps)`);
        fetchJobs();
      } catch (err) {
        notify("Submit failed: " + err.message);
      }
    },
    [fetchJobs],
  );

  const handleCancel = useCallback(
    async (id) => {
      try {
        await cancelJob(id);
        notify("Cancelled");
        fetchJobs();
      } catch (err) {
        notify("Cancel failed: " + err.message);
      }
    },
    [fetchJobs],
  );

  // Apply a pipeline result from any deep-plan job in the job list.
  // Called from the inline "Apply pipeline" button on JobRow.
  const handleApplyPipeline = useCallback((pipeline, url) => {
    setDeepPlanResult(pipeline);
    setDeepPlanStatus("done");
    setAnalysisUrl(url || null);
  }, []);

  // ── Deep Plan ───────────────────────────────────────────────────────────
  const handleDeepPlan = useCallback(async (prompt, currentPipeline) => {
    // Reset state before the async gap to prevent polling the old job ID
    setDeepPlanJobId(null);
    setDeepPlanStatus("running");
    setAnalysisUrl(null);
    setDeepPlanResult(null);

    try {
      let task = prompt;
      if (currentPipeline?.length > 0) {
        task = `## Goal\n${prompt}\n\n## Previous Pipeline\n${JSON.stringify(currentPipeline, null, 2)}\n\nPlease refine this pipeline based on the goal above.`;
      }

      const result = await submitJob({
        task,
        profile: "deep-plan",
        tags: "deep-plan",
        source: "dashboard",
      });
      setDeepPlanJobId(result.id);
    } catch (err) {
      setAnalysisUrl(null);
      notify("Deep Plan failed: " + err.message);
      setDeepPlanStatus("failed");
    }
  }, []);

  // Poll for deep plan job completion (max 10 minutes)
  useEffect(() => {
    if (!deepPlanJobId || deepPlanStatus !== "running") return;

    let polls = 0;
    const MAX_POLLS = 120; // 10 min at 5s intervals

    const poll = async () => {
      polls++;
      if (polls > MAX_POLLS) {
        setDeepPlanStatus("failed");
        notify("Deep Plan timed out");
        return;
      }

      try {
        const job = await getJob(deepPlanJobId);
        if (job.status === "SUCCEEDED") {
          const result = getResult(job);
          if (result?.pipeline) {
            setDeepPlanResult(result.pipeline);
            setDeepPlanStatus("done");
            setAnalysisUrl(result.url || null);
            notify("Deep Plan complete");
          } else {
            setDeepPlanStatus("done");
            setAnalysisUrl(result?.url || null);
            notify("Deep Plan complete (no pipeline returned)");
          }
        } else if (job.status === "FAILED" || job.status === "CANCELLED") {
          setDeepPlanStatus("failed");
          notify("Deep Plan " + job.status.toLowerCase());
        }
      } catch {
        // Retry on next poll
      }
    };

    const id = setInterval(poll, POLL_INTERVAL);
    poll(); // Immediate first check
    return () => clearInterval(id);
  }, [deepPlanJobId, deepPlanStatus]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f9fafb",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        fontFamily:
          "'DM Sans', ui-sans-serif, system-ui, -apple-system, sans-serif",
      }}
    >
      <style>{`
        @keyframes ping {
          75%, 100% { transform: scale(2); opacity: 0; }
        }
        * { box-sizing: border-box; }
        body { margin: 0; }
        ::placeholder { color: #d1d5db; }
      `}</style>

      <div
        style={{
          width: "100%",
          maxWidth: "48rem",
          padding: isMobile ? "32px 16px 96px" : "64px 32px 96px",
        }}
      >
        <PipelineComposer
          agents={agents}
          onSubmit={handlePipelineSubmit}
          onDeepPlan={handleDeepPlan}
          deepPlanStatus={deepPlanStatus}
          deepPlanResult={deepPlanResult}
        />

        {jobs.length > 0 && (
          <div style={{ marginTop: 32 }}>
            <JobList
              jobs={jobs}
              agents={agents}
              onCancel={handleCancel}
              onApplyPipeline={handleApplyPipeline}
              isMobile={isMobile}
            />
          </div>
        )}
      </div>

      {toast && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            fontSize: 12,
            fontWeight: 500,
            background: "#111827",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 8,
            boxShadow:
              "0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)",
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}

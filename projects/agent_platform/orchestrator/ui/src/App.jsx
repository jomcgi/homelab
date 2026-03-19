import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Markdown from "react-markdown";
import { listJobs, submitJob, cancelJob } from "./api.js";

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL = 5000;

const STATUS_META = {
  PENDING: { color: "#f59e0b", label: "pending" },
  RUNNING: { color: "#3b82f6", label: "running" },
  SUCCEEDED: { color: "#22c55e", label: "done" },
  FAILED: { color: "#ef4444", label: "failed" },
  CANCELLED: { color: "#d1d5db", label: "cancelled" },
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

// ─── Plan colors ──────────────────────────────────────────────────────────────

const PLAN_COLORS = [
  { bg: "#ede9fe", fg: "#6d28d9" },
  { bg: "#dbeafe", fg: "#1d4ed8" },
  { bg: "#d1fae5", fg: "#065f46" },
  { bg: "#fef3c7", fg: "#92400e" },
  { bg: "#fce7f3", fg: "#9d174d" },
  { bg: "#e0e7ff", fg: "#3730a3" },
];

function agentColor(agent) {
  let h = 0;
  for (let i = 0; i < agent.length; i++) h = (h * 31 + agent.charCodeAt(i)) | 0;
  return PLAN_COLORS[Math.abs(h) % PLAN_COLORS.length];
}

const STEP_STATUS_MAP = {
  completed: "SUCCEEDED",
  running: "RUNNING",
  failed: "FAILED",
  skipped: "CANCELLED",
  pending: "PENDING",
};

// ─── Output parsing ──────────────────────────────────────────────────────────

const STEP_SEPARATOR = /\n--- pipeline step (\d+): (.+?) ---\n/;

function parseStepOutput(output) {
  if (!output) return [];
  const parts = output.split(STEP_SEPARATOR);
  const steps = [];
  for (let i = 1; i + 2 < parts.length; i += 3) {
    steps.push({
      index: parseInt(parts[i], 10),
      agent: parts[i + 1],
      content: parts[i + 2].trim(),
    });
  }
  return steps;
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

// ─── Pipeline flow (plan steps) ───────────────────────────────────────────────

function PipelineFlow({ plan, activeStep, onStepClick }) {
  if (!plan?.length) return null;

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
      {plan.map((step, i) => {
        const color = agentColor(step.agent);
        const mappedStatus = STEP_STATUS_MAP[step.status] || "PENDING";
        const isSkipped = step.status === "skipped";

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 0,
              minWidth: 0,
              flexShrink: i === plan.length - 1 ? 1 : 0,
            }}
          >
            {/* Connector */}
            {i > 0 && (
              <div
                style={{
                  width: 20,
                  height: 1,
                  background: "#e5e7eb",
                  flexShrink: 0,
                }}
              />
            )}
            {/* Agent pill with status dot */}
            <div
              title={`${step.agent}: ${step.description}`}
              onClick={(e) => {
                e.stopPropagation();
                onStepClick?.(i);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "3px 8px 3px 5px",
                borderRadius: 6,
                background: isSkipped ? "transparent" : color.bg,
                border: isSkipped ? "1px dashed #d1d5db" : "none",
                opacity: isSkipped ? 0.6 : 1,
                flexShrink: 0,
                maxWidth: 120,
                cursor: onStepClick ? "pointer" : "default",
                outline: activeStep === i ? `2px solid ${color.fg}` : "none",
                outlineOffset: 1,
              }}
            >
              <Dot status={mappedStatus} />
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  color: isSkipped ? "#9ca3af" : color.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  textDecoration: isSkipped ? "line-through" : "none",
                }}
              >
                {step.agent}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Step accordion ──────────────────────────────────────────────────────────

function StepAccordion({ step, plan, isOpen, onToggle, stepRef }) {
  const planStep = plan?.[step.index];
  const mappedStatus = planStep
    ? STEP_STATUS_MAP[planStep.status] || "PENDING"
    : "SUCCEEDED";
  const color = agentColor(step.agent);

  return (
    <div ref={stepRef} style={{ borderTop: "1px solid #f3f4f6" }}>
      <button
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          width: "100%",
          padding: "8px 20px",
          fontSize: 11,
          color: "#9ca3af",
          background: isOpen ? "#f9fafb" : "transparent",
          border: "none",
          cursor: "pointer",
          outline: "none",
          transition: "color 0.15s, background 0.15s",
          fontFamily: "inherit",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#374151")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#9ca3af")}
      >
        <ChevronDown size={10} open={isOpen} />
        <Dot status={mappedStatus} />
        <span style={{ fontWeight: 500, color: color.fg }}>{step.agent}</span>
      </button>

      {isOpen && (
        <div
          style={{
            padding: "12px 20px",
            fontSize: 12,
            lineHeight: 1.6,
            color: "#374151",
            overflow: "auto",
            maxHeight: 400,
            borderTop: "1px solid #f3f4f6",
          }}
          className="step-markdown"
        >
          {step.content ? (
            <Markdown>{step.content}</Markdown>
          ) : (
            <span style={{ color: "#d1d5db", fontStyle: "italic" }}>
              No output
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Submit bar ───────────────────────────────────────────────────────────────

function SubmitBar({ onSubmit }) {
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    const t = task.trim();
    if (!t || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(t);
      setTask("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <textarea
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
        }}
        placeholder="Describe a task..."
        rows={3}
        style={{
          width: "100%",
          padding: "12px 14px",
          fontSize: 14,
          fontFamily: "inherit",
          border: "1px solid #e5e7eb",
          borderRadius: 10,
          resize: "vertical",
          outline: "none",
          background: "#fff",
          color: "#1f2937",
          lineHeight: 1.5,
        }}
      />
      <div
        style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}
      >
        <button
          onClick={handleSubmit}
          disabled={!task.trim() || submitting}
          style={{
            padding: "8px 20px",
            fontSize: 13,
            fontWeight: 500,
            background: task.trim() && !submitting ? "#111827" : "#d1d5db",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            cursor: task.trim() && !submitting ? "pointer" : "default",
            fontFamily: "inherit",
            transition: "background 0.15s",
          }}
        >
          {submitting ? "Submitting..." : "Submit"}
        </button>
      </div>
    </div>
  );
}

// ─── Job row ──────────────────────────────────────────────────────────────────

function JobRow({ job, onCancel, isMobile }) {
  const [open, setOpen] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(null);
  const stepRefs = useRef({});
  const canCancel = job.status === "PENDING" || job.status === "RUNNING";
  const result = getResult(job);
  const attempt = job.attempts?.[job.attempts.length - 1];
  const jobSummary = result?.summary || job.failure_summary;
  const hasOutput = attempt?.output || job.status === "PENDING";
  const hasPlan = job.plan?.length > 0;
  const isExpandable = jobSummary || hasOutput || job.summary;
  const stepOutput = useMemo(
    () => (hasPlan ? parseStepOutput(attempt?.output) : []),
    [hasPlan, attempt?.output],
  );

  const handleStepClick = useCallback((i) => {
    setOpen(true);
    setActiveStep((prev) => (prev === i ? null : i));
    setTimeout(() => {
      stepRefs.current[i]?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }, 50);
  }, []);

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

        {/* Task title + plan flow */}
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
          {hasPlan && (
            <div style={{ marginTop: 4 }}>
              <PipelineFlow
                plan={job.plan}
                activeStep={activeStep}
                onStepClick={handleStepClick}
              />
            </div>
          )}
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
          {job.summary && (
            <p
              style={{
                padding: "10px 20px",
                fontSize: 12,
                color: "#6b7280",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {job.summary}
            </p>
          )}

          {jobSummary && (
            <p
              style={{
                padding: "10px 20px",
                fontSize: 12,
                color: job.failure_summary ? "#f87171" : "#6b7280",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {jobSummary}
            </p>
          )}

          {/* Per-step output (pipeline jobs) */}
          {hasPlan && stepOutput.length > 0 && (
            <div>
              {stepOutput.map((step) => (
                <StepAccordion
                  key={step.index}
                  step={step}
                  plan={job.plan}
                  isOpen={activeStep === step.index}
                  onToggle={() =>
                    setActiveStep((prev) =>
                      prev === step.index ? null : step.index,
                    )
                  }
                  stepRef={(el) => (stepRefs.current[step.index] = el)}
                />
              ))}
            </div>
          )}

          {/* Fallback: single output for non-pipeline jobs */}
          {!hasPlan && hasOutput && (
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
                  borderTop:
                    jobSummary || job.summary ? "1px solid #f3f4f6" : "none",
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
              </button>

              {outputOpen && (
                <div
                  style={{
                    padding: "12px 20px",
                    fontSize: 12,
                    lineHeight: 1.6,
                    color: "#374151",
                    overflow: "auto",
                    maxHeight: 400,
                    borderTop: "1px solid #f3f4f6",
                  }}
                  className="step-markdown"
                >
                  <Markdown>{attempt?.output || ""}</Markdown>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Job list with filter + search ───────────────────────────────────────────

function JobList({ jobs, onCancel, isMobile }) {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  const filtered = jobs.filter((j) => {
    const matchStatus = status === "all" || j.status === status;
    const matchSearch =
      !search ||
      (j.task || "").toLowerCase().includes(search.toLowerCase()) ||
      (j.title || "").toLowerCase().includes(search.toLowerCase());
    return matchStatus && matchSearch;
  });

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

      {/* Job list */}
      <div>
        {filtered.length === 0 ? (
          <p style={{ fontSize: 12, color: "#d1d5db", padding: "16px 4px" }}>
            No jobs match
          </p>
        ) : (
          filtered.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onCancel={onCancel}
              isMobile={isMobile}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState(null);
  const [windowWidth, setWindowWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1024,
  );
  const isMobile = windowWidth < 640;
  const notify = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

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

  const handleSubmit = useCallback(
    async (task) => {
      try {
        await submitJob(task);
        notify("Job submitted");
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
        .step-markdown h1, .step-markdown h2, .step-markdown h3 {
          font-size: 13px;
          font-weight: 600;
          margin: 8px 0 4px;
          color: #1f2937;
        }
        .step-markdown p { margin: 4px 0; }
        .step-markdown ul, .step-markdown ol { margin: 4px 0; padding-left: 20px; }
        .step-markdown code {
          font-family: monospace;
          font-size: 11px;
          background: #f3f4f6;
          padding: 1px 4px;
          border-radius: 3px;
        }
        .step-markdown pre {
          background: #f3f4f6;
          padding: 8px 12px;
          border-radius: 6px;
          overflow-x: auto;
          margin: 4px 0;
        }
        .step-markdown pre code { background: none; padding: 0; }
      `}</style>

      <div
        style={{
          width: "100%",
          maxWidth: "48rem",
          padding: isMobile ? "32px 16px 96px" : "64px 32px 96px",
        }}
      >
        <SubmitBar onSubmit={handleSubmit} />

        {jobs.length > 0 && (
          <div style={{ marginTop: 32 }}>
            <JobList jobs={jobs} onCancel={handleCancel} isMobile={isMobile} />
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

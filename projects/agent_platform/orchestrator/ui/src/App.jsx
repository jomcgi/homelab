import { useState, useEffect, useCallback } from "react";
import { listJobs, listAgents, submitPipeline, cancelJob } from "./api.js";
import PipelineComposer from "./PipelineComposer.jsx";

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

// ─── Job row ──────────────────────────────────────────────────────────────────

function JobRow({ job, onCancel, isMobile }) {
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
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 4px",
        }}
      >
        <Dot status={job.status} />

        {/* Task title only */}
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
            {job.task}
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
              onClick={() => setOpen((o) => !o)}
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
              onClick={() => onCancel(job.id)}
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

      {/* Level 1: Summary */}
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

          {/* Level 2: Output toggle */}
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

// ─── Job list with filter + search ───────────────────────────────────────────

function JobList({ jobs, onCancel, isMobile }) {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  const visible = jobs.filter((j) => {
    const matchStatus = status === "all" || j.status === status;
    const matchSearch =
      !search || j.task.toLowerCase().includes(search.toLowerCase());
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

      {/* List */}
      <div>
        {visible.length === 0 ? (
          <p style={{ fontSize: 12, color: "#d1d5db", padding: "16px 4px" }}>
            No jobs match
          </p>
        ) : (
          visible.map((job) => (
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
  const [agents, setAgents] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [toast, setToast] = useState(null);
  const [windowWidth, setWindowWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1024,
  );
  const isMobile = windowWidth < 640;

  const notify = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  // Fetch agent registry on mount
  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents || []);
        setProfiles(data.profiles || []);
      })
      .catch(() => {
        setAgents([]);
        setProfiles([]);
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
          profiles={profiles}
          onSubmit={handlePipelineSubmit}
        />

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

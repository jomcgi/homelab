import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { listJobs, submitJob, cancelJob, getJobOutput } from "./api.js";

// ─── constants ────────────────────────────────────────────────────────────────

const STATUSES = ["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"];
const STATUS_COLOR = {
  PENDING: "#6b7280",
  RUNNING: "#2563eb",
  SUCCEEDED: "#16a34a",
  FAILED: "#dc2626",
  CANCELLED: "#9ca3af",
};
const TABS = [
  { label: "All", key: null },
  { label: "Pending", key: "PENDING" },
  { label: "Running", key: "RUNNING" },
  { label: "Succeeded", key: "SUCCEEDED" },
  { label: "Failed", key: "FAILED" },
];
const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 1200;
const POLL_INTERVAL = 5000;

// ─── utilities ────────────────────────────────────────────────────────────────

function age(ts) {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function duration(start, end) {
  if (!start) return "—";
  const ms = (end ? new Date(end) : new Date()) - new Date(start);
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

// Auto-link URLs in text, shorten github PR URLs
function Linkified({ text }) {
  if (!text) return null;
  const URL_RE = /(https?:\/\/[^\s]+)/g;
  const parts = [];
  let last = 0;
  let m;
  while ((m = URL_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const url = m[1];
    let label = url;
    const prMatch = url.match(/github\.com\/[^/]+\/[^/]+\/pull\/(\d+)/);
    if (prMatch) label = `PR #${prMatch[1]}`;
    parts.push(
      <a
        key={m.index}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: "#2563eb", textDecoration: "underline" }}
      >
        {label}
      </a>,
    );
    last = m.index + url.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

// ─── sub-components ───────────────────────────────────────────────────────────

function StatusDot({ status }) {
  const color = STATUS_COLOR[status] || "#6b7280";
  return (
    <span
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
      }}
    >
      {status === "RUNNING" && (
        <span
          style={{
            position: "absolute",
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: color,
            opacity: 0.4,
            animation: "ripple 1.4s ease-out infinite",
          }}
        />
      )}
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
      />
    </span>
  );
}

function Tag({ label, onClick, active }) {
  return (
    <span
      onClick={onClick}
      style={{
        display: "inline-block",
        padding: "1px 6px",
        borderRadius: 4,
        fontSize: 11,
        fontFamily: "monospace",
        background: active ? "#2563eb" : "#f1f5f9",
        color: active ? "#fff" : "#374151",
        cursor: onClick ? "pointer" : "default",
        userSelect: "none",
        border: active ? "1px solid #2563eb" : "1px solid #e2e8f0",
      }}
    >
      {label}
    </span>
  );
}

function Kbd({ children }) {
  return (
    <kbd
      style={{
        display: "inline-block",
        padding: "1px 5px",
        borderRadius: 3,
        fontSize: 11,
        fontFamily: "monospace",
        background: "#f1f5f9",
        border: "1px solid #d1d5db",
        color: "#374151",
      }}
    >
      {children}
    </kbd>
  );
}

function TagDropdown({ allTags, activeTag, onSelect }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (allTags.length === 0) return null;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: "3px 10px",
          borderRadius: 6,
          border: "1px solid #d1d5db",
          background: activeTag ? "#2563eb" : "#fff",
          color: activeTag ? "#fff" : "#374151",
          cursor: "pointer",
          fontSize: 13,
        }}
      >
        {activeTag ? `#${activeTag}` : "Tags ▾"}
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "110%",
            left: 0,
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
            minWidth: 160,
            zIndex: 100,
            maxHeight: 300,
            overflowY: "auto",
          }}
        >
          {activeTag && (
            <div
              onClick={() => {
                onSelect(null);
                setOpen(false);
              }}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                color: "#6b7280",
                fontSize: 13,
              }}
            >
              Clear filter
            </div>
          )}
          {allTags.map(([tag, count]) => (
            <div
              key={tag}
              onClick={() => {
                onSelect(tag);
                setOpen(false);
              }}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                fontSize: 13,
                background: tag === activeTag ? "#eff6ff" : "transparent",
              }}
            >
              <span style={{ fontFamily: "monospace" }}>#{tag}</span>
              <span style={{ color: "#9ca3af" }}>{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function JobRow({ job, selected, dismissed, onSelect }) {
  if (dismissed) return null;
  const attempt = job.attempts?.length
    ? job.attempts[job.attempts.length - 1]
    : null;
  return (
    <div
      onClick={onSelect}
      style={{
        padding: "10px 16px",
        borderBottom: "1px solid #f1f5f9",
        cursor: "pointer",
        background: selected ? "#eff6ff" : "transparent",
        borderLeft: selected ? "3px solid #2563eb" : "3px solid transparent",
        transition: "background 0.1s",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 4,
        }}
      >
        <StatusDot status={job.status} />
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            color: "#9ca3af",
            flexShrink: 0,
          }}
        >
          {job.id.slice(-8)}
        </span>
        <span
          style={{
            flex: 1,
            fontSize: 13,
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={job.task}
        >
          {job.task}
        </span>
        <span style={{ fontSize: 11, color: "#9ca3af", flexShrink: 0 }}>
          {age(job.created_at)}
        </span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          paddingLeft: 16,
        }}
      >
        {job.profile && (
          <span
            style={{
              fontSize: 11,
              color: "#6b7280",
              background: "#f9fafb",
              border: "1px solid #e5e7eb",
              borderRadius: 3,
              padding: "0 4px",
            }}
          >
            {job.profile}
          </span>
        )}
        {(job.tags || []).map((t) => (
          <Tag key={t} label={t} />
        ))}
        {attempt && (
          <span style={{ fontSize: 11, color: "#9ca3af", marginLeft: "auto" }}>
            {duration(attempt.started_at, attempt.finished_at)}
          </span>
        )}
      </div>
    </div>
  );
}

function Detail({ job, output, onCancel, onFollowOn, onDismiss }) {
  const attempt = job.attempts?.length
    ? job.attempts[job.attempts.length - 1]
    : null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: "1px solid #e5e7eb",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 8,
          }}
        >
          <StatusDot status={job.status} />
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              flex: 1,
              color: STATUS_COLOR[job.status],
            }}
          >
            {job.status}
          </span>
          <span
            style={{ fontFamily: "monospace", fontSize: 11, color: "#9ca3af" }}
          >
            {job.id}
          </span>
        </div>
        <div
          style={{
            fontSize: 14,
            color: "#111827",
            marginBottom: 10,
            lineHeight: 1.5,
          }}
        >
          {job.task}
        </div>
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            marginBottom: 10,
          }}
        >
          {(job.tags || []).map((t) => (
            <Tag key={t} label={t} />
          ))}
          {job.profile && (
            <span
              style={{
                fontSize: 11,
                color: "#6b7280",
                background: "#f9fafb",
                border: "1px solid #e5e7eb",
                borderRadius: 3,
                padding: "0 6px",
              }}
            >
              profile: {job.profile}
            </span>
          )}
        </div>
        <div
          style={{ fontSize: 11, color: "#9ca3af", display: "flex", gap: 16 }}
        >
          <span>Created {new Date(job.created_at).toLocaleString()}</span>
          {attempt && (
            <span>
              Duration: {duration(attempt.started_at, attempt.finished_at)}
            </span>
          )}
          {job.attempts?.length > 0 && (
            <span>Attempts: {job.attempts.length}</span>
          )}
          {typeof attempt?.exit_code === "number" && (
            <span>Exit: {attempt.exit_code}</span>
          )}
        </div>
        {/* Actions */}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {(job.status === "PENDING" || job.status === "RUNNING") && (
            <button
              onClick={onCancel}
              style={{
                padding: "4px 12px",
                borderRadius: 6,
                border: "1px solid #fca5a5",
                background: "#fff1f2",
                color: "#dc2626",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              Cancel <Kbd>c</Kbd>
            </button>
          )}
          <button
            onClick={onFollowOn}
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "#f9fafb",
              color: "#374151",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Follow-on <Kbd>f</Kbd>
          </button>
          <button
            onClick={onDismiss}
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "#f9fafb",
              color: "#374151",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Dismiss <Kbd>e</Kbd>
          </button>
        </div>
      </div>

      {/* Output */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
        {output ? (
          <>
            {output.truncated && (
              <div
                style={{
                  padding: "6px 10px",
                  background: "#fffbeb",
                  border: "1px solid #fde68a",
                  borderRadius: 4,
                  fontSize: 12,
                  color: "#92400e",
                  marginBottom: 10,
                }}
              >
                Output truncated — showing tail only
              </div>
            )}
            <pre
              style={{
                margin: 0,
                fontFamily: "monospace",
                fontSize: 12,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                color: "#1f2937",
              }}
            >
              <Linkified text={output.output} />
            </pre>
          </>
        ) : attempt ? (
          <div style={{ color: "#9ca3af", fontSize: 13 }}>Loading output…</div>
        ) : (
          <div style={{ color: "#9ca3af", fontSize: 13 }}>No output yet.</div>
        )}
      </div>
    </div>
  );
}

function SubmitModal({ onClose, onSubmit, prefill }) {
  const [task, setTask] = useState(prefill?.task || "");
  const [profile, setProfile] = useState(prefill?.profile || "");
  const [tags, setTags] = useState(prefill?.tags || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!task.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ task: task.trim(), profile, tags });
      onClose();
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          padding: 28,
          width: 560,
          maxWidth: "95vw",
          boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
        }}
      >
        <h2 style={{ margin: "0 0 20px", fontSize: 18, fontWeight: 600 }}>
          Submit Job
        </h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label
              style={{
                display: "block",
                fontSize: 13,
                fontWeight: 500,
                marginBottom: 6,
              }}
            >
              Task *
            </label>
            <textarea
              ref={textareaRef}
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Describe the task for the agent…"
              rows={5}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #d1d5db",
                fontSize: 14,
                fontFamily: "inherit",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
          </div>
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 500,
                  marginBottom: 6,
                }}
              >
                Profile
              </label>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: "1px solid #d1d5db",
                  fontSize: 14,
                  background: "#fff",
                }}
              >
                <option value="">Default</option>
                <option value="ci-debug">ci-debug</option>
                <option value="code-fix">code-fix</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 500,
                  marginBottom: 6,
                }}
              >
                Tags (comma-separated)
              </label>
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="e.g. ci, homelab"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: 8,
                  border: "1px solid #d1d5db",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>
          {error && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "#fef2f2",
                border: "1px solid #fca5a5",
                borderRadius: 6,
                fontSize: 13,
                color: "#dc2626",
              }}
            >
              {error}
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "8px 18px",
                borderRadius: 8,
                border: "1px solid #d1d5db",
                background: "#fff",
                cursor: "pointer",
                fontSize: 14,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !task.trim()}
              style={{
                padding: "8px 18px",
                borderRadius: 8,
                border: "none",
                background: submitting || !task.trim() ? "#93c5fd" : "#2563eb",
                color: "#fff",
                cursor: submitting || !task.trim() ? "not-allowed" : "pointer",
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function HelpOverlay({ onClose }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape" || e.key === "?") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shortcuts = [
    ["j / ↓", "Select next job"],
    ["k / ↑", "Select previous job"],
    ["n", "New job"],
    ["e", "Dismiss selected"],
    ["c", "Cancel selected"],
    ["f", "Follow-on job"],
    ["1–5", "Switch filter tab"],
    ["?", "Toggle help"],
  ];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          padding: 28,
          width: 400,
          boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
        }}
      >
        <h2 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
          Keyboard Shortcuts
        </h2>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {shortcuts.map(([key, desc]) => (
              <tr key={key}>
                <td style={{ padding: "6px 0", width: 80 }}>
                  <Kbd>{key}</Kbd>
                </td>
                <td
                  style={{ padding: "6px 0", fontSize: 13, color: "#374151" }}
                >
                  {desc}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ marginTop: 16, textAlign: "right" }}>
          <button
            onClick={onClose}
            style={{
              padding: "6px 16px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── main dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [dismissed, setDismissed] = useState(new Set());
  const [tabKey, setTabKey] = useState(null);
  const [tagFilter, setTagFilter] = useState(null);
  const [showSubmit, setShowSubmit] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [submitPrefill, setSubmitPrefill] = useState(null);
  const [output, setOutput] = useState(null);
  const [sidebarWidth, setSidebarWidth] = useState(400);
  const dragging = useRef(false);
  const dragStart = useRef(0);
  const dragInitial = useRef(0);

  // Fetch jobs
  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs({
        status: tabKey || undefined,
        tags: tagFilter || undefined,
        limit: 100,
      });
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tabKey, tagFilter]);

  useEffect(() => {
    setLoading(true);
    fetchJobs();
    const id = setInterval(fetchJobs, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchJobs]);

  // Fetch output for selected running/completed job
  const selectedJob = useMemo(
    () => jobs.find((j) => j.id === selectedId) || null,
    [jobs, selectedId],
  );

  useEffect(() => {
    if (!selectedJob) {
      setOutput(null);
      return;
    }
    if (!selectedJob.attempts?.length) {
      setOutput(null);
      return;
    }

    let cancelled = false;
    async function fetchOutput() {
      try {
        const data = await getJobOutput(selectedJob.id);
        if (!cancelled) setOutput(data);
      } catch {
        if (!cancelled) setOutput(null);
      }
    }

    fetchOutput();

    // Poll if running
    if (selectedJob.status === "RUNNING") {
      const id = setInterval(fetchOutput, POLL_INTERVAL);
      return () => {
        cancelled = true;
        clearInterval(id);
      };
    }
    return () => {
      cancelled = true;
    };
  }, [selectedJob?.id, selectedJob?.status, selectedJob?.attempts?.length]);

  // Visible jobs (not dismissed)
  const visibleJobs = useMemo(
    () => jobs.filter((j) => !dismissed.has(j.id)),
    [jobs, dismissed],
  );

  // All tags with counts
  const allTags = useMemo(() => {
    const map = {};
    jobs.forEach((j) =>
      (j.tags || []).forEach((t) => (map[t] = (map[t] || 0) + 1)),
    );
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [jobs]);

  // Stats computed from jobs
  const stats = useMemo(() => {
    const s = { running: 0, pending: 0, succeeded: 0, failed: 0, cancelled: 0 };
    jobs.forEach((j) => {
      const k = j.status.toLowerCase();
      if (k in s) s[k]++;
    });
    return s;
  }, [jobs]);

  // Selected index for keyboard nav
  const selectedIdx = useMemo(
    () => visibleJobs.findIndex((j) => j.id === selectedId),
    [visibleJobs, selectedId],
  );

  function selectIdx(i) {
    const clamped = Math.max(0, Math.min(i, visibleJobs.length - 1));
    setSelectedId(visibleJobs[clamped]?.id || null);
  }

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e) {
      if (showSubmit || showHelp) return;
      if (
        e.target.tagName === "INPUT" ||
        e.target.tagName === "TEXTAREA" ||
        e.target.tagName === "SELECT"
      )
        return;
      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          selectIdx(selectedIdx + 1);
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          selectIdx(selectedIdx - 1);
          break;
        case "n":
          setSubmitPrefill(null);
          setShowSubmit(true);
          break;
        case "e":
          if (selectedId) setDismissed((d) => new Set([...d, selectedId]));
          break;
        case "c":
          if (
            selectedJob &&
            (selectedJob.status === "PENDING" ||
              selectedJob.status === "RUNNING")
          ) {
            handleCancel(selectedJob);
          }
          break;
        case "f":
          if (selectedJob) handleFollowOn(selectedJob);
          break;
        case "?":
          setShowHelp((h) => !h);
          break;
        case "1":
          setTabKey(null);
          break;
        case "2":
          setTabKey("PENDING");
          break;
        case "3":
          setTabKey("RUNNING");
          break;
        case "4":
          setTabKey("SUCCEEDED");
          break;
        case "5":
          setTabKey("FAILED");
          break;
        default:
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showSubmit, showHelp, selectedIdx, selectedId, selectedJob, visibleJobs]);

  async function handleCancel(job) {
    try {
      await cancelJob(job.id);
      fetchJobs();
    } catch (err) {
      alert("Cancel failed: " + err.message);
    }
  }

  function handleFollowOn(job) {
    const outputTail = output?.output
      ? "\n\nPrevious output tail:\n" + output.output.slice(-500)
      : "";
    setSubmitPrefill({
      task: `Follow-on to job ${job.id.slice(-8)}: ${job.task}${outputTail}`,
      profile: job.profile || "",
      tags: (job.tags || []).join(", "),
    });
    setShowSubmit(true);
  }

  async function handleSubmit({ task, profile, tags }) {
    await submitJob({ task, profile, tags });
    fetchJobs();
  }

  // Sidebar resize drag
  function onDragStart(e) {
    dragging.current = true;
    dragStart.current = e.clientX;
    dragInitial.current = sidebarWidth;
    e.preventDefault();
  }

  useEffect(() => {
    function onMove(e) {
      if (!dragging.current) return;
      const delta = dragStart.current - e.clientX;
      setSidebarWidth(
        Math.max(
          SIDEBAR_MIN,
          Math.min(SIDEBAR_MAX, dragInitial.current + delta),
        ),
      );
    }
    function onUp() {
      dragging.current = false;
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: "system-ui, sans-serif",
        background: "#f8fafc",
      }}
    >
      {/* ripple keyframes */}
      <style>{`
        @keyframes ripple {
          0% { transform: scale(1); opacity: 0.4; }
          100% { transform: scale(3); opacity: 0; }
        }
        * { box-sizing: border-box; }
        body { margin: 0; }
      `}</style>

      {/* Top bar */}
      <div
        style={{
          height: 52,
          background: "#fff",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          padding: "0 20px",
          gap: 20,
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>
          🦆 Agent Orchestrator
        </span>
        <div
          style={{ display: "flex", gap: 16, fontSize: 12, color: "#6b7280" }}
        >
          <span>
            <span style={{ color: "#2563eb", fontWeight: 600 }}>
              {stats.running}
            </span>{" "}
            running
          </span>
          <span>
            <span style={{ color: "#6b7280", fontWeight: 600 }}>
              {stats.pending}
            </span>{" "}
            pending
          </span>
          <span>
            <span style={{ color: "#16a34a", fontWeight: 600 }}>
              {stats.succeeded}
            </span>{" "}
            succeeded
          </span>
          <span>
            <span style={{ color: "#dc2626", fontWeight: 600 }}>
              {stats.failed}
            </span>{" "}
            failed
          </span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            onClick={() => setShowHelp(true)}
            style={{
              padding: "5px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: "pointer",
              fontSize: 13,
              color: "#374151",
            }}
          >
            ? Help
          </button>
          <button
            onClick={() => {
              setSubmitPrefill(null);
              setShowSubmit(true);
            }}
            style={{
              padding: "5px 14px",
              borderRadius: 6,
              border: "none",
              background: "#2563eb",
              color: "#fff",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            + New Job
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div
        style={{
          height: 44,
          background: "#fff",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          gap: 4,
          flexShrink: 0,
        }}
      >
        {TABS.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setTabKey(tab.key)}
            style={{
              padding: "4px 14px",
              borderRadius: 6,
              border: "none",
              background: tabKey === tab.key ? "#eff6ff" : "transparent",
              color: tabKey === tab.key ? "#2563eb" : "#6b7280",
              fontWeight: tabKey === tab.key ? 600 : 400,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {tab.label}
            <Kbd>{i + 1}</Kbd>
          </button>
        ))}
        <div style={{ marginLeft: "auto" }}>
          <TagDropdown
            allTags={allTags}
            activeTag={tagFilter}
            onSelect={setTagFilter}
          />
        </div>
        <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 8 }}>
          {total} total
        </span>
      </div>

      {/* Content area */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Job list */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            background: "#fff",
            borderRight: "1px solid #e5e7eb",
          }}
        >
          {loading && (
            <div
              style={{
                padding: 32,
                color: "#9ca3af",
                textAlign: "center",
                fontSize: 13,
              }}
            >
              Loading…
            </div>
          )}
          {error && (
            <div
              style={{
                margin: 16,
                padding: 12,
                background: "#fef2f2",
                border: "1px solid #fca5a5",
                borderRadius: 6,
                fontSize: 13,
                color: "#dc2626",
              }}
            >
              Error: {error}
            </div>
          )}
          {!loading && !error && visibleJobs.length === 0 && (
            <div
              style={{
                padding: 40,
                color: "#9ca3af",
                textAlign: "center",
                fontSize: 13,
              }}
            >
              No jobs found.
            </div>
          )}
          {visibleJobs.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              selected={job.id === selectedId}
              dismissed={false}
              onSelect={() =>
                setSelectedId(job.id === selectedId ? null : job.id)
              }
            />
          ))}
        </div>

        {/* Detail pane (shown when a job is selected) */}
        {selectedJob && (
          <>
            {/* Drag handle */}
            <div
              onMouseDown={onDragStart}
              style={{
                width: 4,
                cursor: "col-resize",
                background: "#e5e7eb",
                flexShrink: 0,
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "#93c5fd")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "#e5e7eb")
              }
            />
            <div
              style={{
                width: sidebarWidth,
                flexShrink: 0,
                overflowY: "auto",
                background: "#fff",
              }}
            >
              <Detail
                job={selectedJob}
                output={output}
                onCancel={() => handleCancel(selectedJob)}
                onFollowOn={() => handleFollowOn(selectedJob)}
                onDismiss={() => {
                  setDismissed((d) => new Set([...d, selectedJob.id]));
                  setSelectedId(null);
                }}
              />
            </div>
          </>
        )}
      </div>

      {showSubmit && (
        <SubmitModal
          prefill={submitPrefill}
          onClose={() => setShowSubmit(false)}
          onSubmit={handleSubmit}
        />
      )}
      {showHelp && <HelpOverlay onClose={() => setShowHelp(false)} />}
    </div>
  );
}

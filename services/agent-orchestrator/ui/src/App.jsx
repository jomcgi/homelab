import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { listJobs, submitJob, cancelJob, getJobOutput } from './api.js';

// ─── colour tokens ───────────────────────────────────────────────────────────
const C = {
  bg: '#f9f9f8',
  surface: '#ffffff',
  border: '#e4e4e0',
  borderHover: '#c8c8c4',
  text: '#1a1a18',
  muted: '#6b6b68',
  accent: '#2563eb',
  accentBg: '#eff6ff',
  running: '#16a34a',
  runningBg: '#f0fdf4',
  pending: '#d97706',
  pendingBg: '#fffbeb',
  failed: '#dc2626',
  failedBg: '#fef2f2',
  cancelled: '#9ca3af',
  cancelledBg: '#f9fafb',
  succeeded: '#16a34a',
  succeededBg: '#f0fdf4',
};

const STATUS_COLOURS = {
  running: { dot: C.running, bg: C.runningBg, label: 'Running' },
  pending: { dot: C.pending, bg: C.pendingBg, label: 'Pending' },
  failed: { dot: C.failed, bg: C.failedBg, label: 'Failed' },
  cancelled: { dot: C.cancelled, bg: C.cancelledBg, label: 'Cancelled' },
  succeeded: { dot: C.succeeded, bg: C.succeededBg, label: 'Succeeded' },
};

const TABS = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'succeeded', label: 'Succeeded' },
  { key: 'failed', label: 'Failed' },
  { key: 'cancelled', label: 'Cancelled' },
];

const PROFILES = ['', 'ci-debug', 'code-fix'];

// ─── helpers ─────────────────────────────────────────────────────────────────
function fmtDuration(start, end) {
  if (!start) return '—';
  const ms = (end ? new Date(end) : Date.now()) - new Date(start);
  if (ms < 0) return '—';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return `${m}m ${rem}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return d.toLocaleDateString();
}

// Linkify URLs in output text
function Linkified({ text }) {
  if (!text) return null;
  const URL_RE = /https?:\/\/[^\s)>"\]]+/g;
  const parts = [];
  let last = 0;
  let m;
  while ((m = URL_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const url = m[0];
    // Shorten GitHub PR URLs: github.com/owner/repo/pull/N -> #N (owner/repo)
    let label = url;
    const ghPr = url.match(/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/);
    if (ghPr) label = `#${ghPr[2]} (${ghPr[1]})`;
    else if (url.length > 60) label = url.slice(0, 57) + '…';
    parts.push(
      <a
        key={m.index}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: C.accent, textDecoration: 'underline' }}
      >
        {label}
      </a>,
    );
    last = m.index + url.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

// ─── StatusDot ───────────────────────────────────────────────────────────────
function StatusDot({ status }) {
  const col = STATUS_COLOURS[status] || STATUS_COLOURS.pending;
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 10, height: 10, flexShrink: 0 }}>
      {status === 'running' && (
        <span
          style={{
            position: 'absolute',
            inset: -3,
            borderRadius: '50%',
            background: col.dot,
            opacity: 0.3,
            animation: 'ripple 1.4s ease-out infinite',
          }}
        />
      )}
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: col.dot, flexShrink: 0 }} />
    </span>
  );
}

// ─── Tag ─────────────────────────────────────────────────────────────────────
function Tag({ label, onClick, active }) {
  return (
    <span
      onClick={onClick}
      style={{
        display: 'inline-block',
        padding: '1px 6px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 500,
        background: active ? C.accent : '#e8e8e4',
        color: active ? '#fff' : C.muted,
        cursor: onClick ? 'pointer' : 'default',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
}

// ─── Kbd ─────────────────────────────────────────────────────────────────────
function Kbd({ children }) {
  return (
    <kbd
      style={{
        display: 'inline-block',
        padding: '1px 5px',
        borderRadius: 3,
        border: `1px solid ${C.border}`,
        background: C.surface,
        fontSize: 11,
        fontFamily: 'monospace',
        color: C.text,
        minWidth: 18,
        textAlign: 'center',
      }}
    >
      {children}
    </kbd>
  );
}

// ─── TagDropdown ─────────────────────────────────────────────────────────────
function TagDropdown({ jobs, activeTag, onSelect }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const tagCounts = useMemo(() => {
    const counts = {};
    for (const job of jobs) {
      for (const t of job.tags || []) {
        counts[t] = (counts[t] || 0) + 1;
      }
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [jobs]);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (tagCounts.length === 0) return null;

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: '3px 8px',
          border: `1px solid ${activeTag ? C.accent : C.border}`,
          borderRadius: 4,
          background: activeTag ? C.accentBg : C.surface,
          color: activeTag ? C.accent : C.text,
          fontSize: 12,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        {activeTag ? `tag: ${activeTag}` : 'Tags'} <span style={{ fontSize: 10 }}>▾</span>
      </button>
      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: 4,
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            zIndex: 100,
            minWidth: 160,
            overflow: 'hidden',
          }}
        >
          {activeTag && (
            <div
              onClick={() => { onSelect(''); setOpen(false); }}
              style={{ padding: '6px 12px', fontSize: 12, cursor: 'pointer', color: C.muted, borderBottom: `1px solid ${C.border}` }}
            >
              Clear filter
            </div>
          )}
          {tagCounts.map(([tag, count]) => (
            <div
              key={tag}
              onClick={() => { onSelect(tag); setOpen(false); }}
              style={{
                padding: '6px 12px',
                fontSize: 12,
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: tag === activeTag ? C.accentBg : 'transparent',
                color: tag === activeTag ? C.accent : C.text,
              }}
            >
              <span>{tag}</span>
              <span style={{ color: C.muted, fontSize: 11 }}>{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── JobRow ───────────────────────────────────────────────────────────────────
function JobRow({ job, selected, dismissed, onSelect }) {
  if (dismissed) return null;
  const col = STATUS_COLOURS[job.status] || STATUS_COLOURS.pending;
  return (
    <div
      onClick={() => onSelect(job.id)}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '9px 14px',
        cursor: 'pointer',
        background: selected ? C.accentBg : 'transparent',
        borderLeft: `2px solid ${selected ? C.accent : 'transparent'}`,
        borderBottom: `1px solid ${C.border}`,
        transition: 'background 0.1s',
      }}
    >
      <div style={{ paddingTop: 5 }}>
        <StatusDot status={job.status} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: col.dot,
              background: col.bg,
              padding: '1px 5px',
              borderRadius: 3,
              textTransform: 'uppercase',
              letterSpacing: '0.03em',
              flexShrink: 0,
            }}
          >
            {col.label}
          </span>
          {(job.tags || []).slice(0, 3).map((t) => (
            <Tag key={t} label={t} />
          ))}
          {job.source && job.source !== 'api' && (
            <span style={{ fontSize: 11, color: C.muted, flexShrink: 0 }}>{job.source}</span>
          )}
        </div>
        <div
          style={{
            fontSize: 13,
            color: C.text,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            lineHeight: 1.4,
          }}
        >
          {job.task}
        </div>
        <div style={{ fontSize: 11, color: C.muted, marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
          {job.id.slice(0, 10)}… · {fmtTime(job.created_at)} · {fmtDuration(job.created_at, job.updated_at)}
        </div>
      </div>
    </div>
  );
}

// ─── Detail ──────────────────────────────────────────────────────────────────
function Detail({ jobId, jobs, onCancel, onDismiss, onFollowOn }) {
  const [output, setOutput] = useState(null);
  const [outputErr, setOutputErr] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const outputRef = useRef(null);
  const [follow, setFollow] = useState(true);

  const job = jobs.find((j) => j.id === jobId);

  // Poll output for running jobs
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    async function fetchOutput() {
      try {
        const data = await getJobOutput(jobId);
        if (!cancelled) {
          setOutput(data);
          setOutputErr(null);
        }
      } catch (e) {
        if (!cancelled) setOutputErr(e.message);
      }
    }

    fetchOutput();
    if (job && job.status === 'running') {
      const id = setInterval(fetchOutput, 5000);
      return () => { cancelled = true; clearInterval(id); };
    }
    return () => { cancelled = true; };
  }, [jobId, job?.status]);

  // Auto-scroll output when following
  useEffect(() => {
    if (follow && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output, follow]);

  if (!job) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: C.muted,
          fontSize: 13,
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <span style={{ fontSize: 32 }}>✦</span>
        <span>Select a job to view details</span>
        <span style={{ fontSize: 12 }}>
          <Kbd>n</Kbd> new job &nbsp;·&nbsp; <Kbd>?</Kbd> help
        </span>
      </div>
    );
  }

  const col = STATUS_COLOURS[job.status] || STATUS_COLOURS.pending;
  const canCancel = job.status === 'pending' || job.status === 'running';

  async function handleCancel() {
    setCancelling(true);
    try {
      await cancelJob(job.id);
      onCancel();
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <StatusDot status={job.status} />
            <span style={{ fontSize: 13, fontWeight: 600, color: col.dot, background: col.bg, padding: '1px 6px', borderRadius: 3, textTransform: 'uppercase' }}>
              {col.label}
            </span>
            {job.profile && <span style={{ fontSize: 11, color: C.muted, fontStyle: 'italic' }}>{job.profile}</span>}
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            {canCancel && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                style={{
                  padding: '3px 10px',
                  border: `1px solid ${C.failed}`,
                  borderRadius: 4,
                  background: 'transparent',
                  color: C.failed,
                  fontSize: 12,
                  cursor: 'pointer',
                  opacity: cancelling ? 0.6 : 1,
                }}
              >
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            <button
              onClick={() => onFollowOn(job)}
              style={{
                padding: '3px 10px',
                border: `1px solid ${C.border}`,
                borderRadius: 4,
                background: 'transparent',
                color: C.text,
                fontSize: 12,
                cursor: 'pointer',
              }}
              title="Create follow-on job (f)"
            >
              Follow-on
            </button>
            <button
              onClick={() => onDismiss(job.id)}
              style={{
                padding: '3px 10px',
                border: `1px solid ${C.border}`,
                borderRadius: 4,
                background: 'transparent',
                color: C.muted,
                fontSize: 12,
                cursor: 'pointer',
              }}
              title="Dismiss (e)"
            >
              Dismiss
            </button>
          </div>
        </div>

        <div style={{ fontSize: 14, color: C.text, lineHeight: 1.5, marginBottom: 8 }}>{job.task}</div>

        {(job.tags || []).length > 0 && (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {job.tags.map((t) => <Tag key={t} label={t} />)}
          </div>
        )}

        <div style={{ fontSize: 11, color: C.muted, marginTop: 8, fontVariantNumeric: 'tabular-nums', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span>ID: <code style={{ fontFamily: 'monospace' }}>{job.id}</code></span>
          <span>Created: {new Date(job.created_at).toLocaleString()}</span>
          <span>Duration: {fmtDuration(job.created_at, job.updated_at)}</span>
          {job.max_retries !== undefined && <span>Retries: {(job.attempts || []).length}/{job.max_retries}</span>}
          {job.source && <span>Source: {job.source}</span>}
        </div>
      </div>

      {/* Output */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '8px 18px 4px', borderBottom: `1px solid ${C.border}`, flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: C.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Output</span>
          {output && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {output.truncated && (
                <span style={{ fontSize: 11, color: C.pending }}>truncated</span>
              )}
              <label style={{ fontSize: 11, color: C.muted, display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} style={{ cursor: 'pointer' }} />
                follow
              </label>
            </div>
          )}
        </div>
        <div
          ref={outputRef}
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '12px 18px',
            fontFamily: 'ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace',
            fontSize: 12,
            lineHeight: 1.6,
            color: C.text,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            background: '#fafaf9',
          }}
        >
          {outputErr && <span style={{ color: C.muted, fontStyle: 'italic' }}>No output available</span>}
          {!outputErr && !output && <span style={{ color: C.muted, fontStyle: 'italic' }}>Loading…</span>}
          {output && output.output ? (
            <Linkified text={output.output} />
          ) : (
            !outputErr && output && <span style={{ color: C.muted, fontStyle: 'italic' }}>No output yet</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── SubmitModal ──────────────────────────────────────────────────────────────
function SubmitModal({ initialTask, initialTags, onClose, onSubmitted }) {
  const [task, setTask] = useState(initialTask || '');
  const [profile, setProfile] = useState('');
  const [tags, setTags] = useState(initialTags || '');
  const [source, setSource] = useState('dashboard');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!task.trim()) { setError('Task is required'); return; }
    setLoading(true);
    setError('');
    try {
      const job = await submitJob({ task: task.trim(), profile, tags, source });
      onSubmitted(job);
    } catch (err) {
      setError(err.message || 'Failed to submit job');
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') onClose();
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit(e);
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.3)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: C.surface,
          borderRadius: 10,
          padding: 24,
          width: 520,
          maxWidth: '90vw',
          boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
        onKeyDown={handleKeyDown}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>New Job</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: C.muted, lineHeight: 1 }}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Task *
          </label>
          <textarea
            ref={textareaRef}
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={5}
            placeholder="Describe what the agent should do…"
            style={{
              width: '100%',
              padding: '8px 10px',
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              fontSize: 13,
              lineHeight: 1.5,
              resize: 'vertical',
              outline: 'none',
              fontFamily: 'inherit',
              boxSizing: 'border-box',
            }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Profile
              </label>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 8px',
                  border: `1px solid ${C.border}`,
                  borderRadius: 6,
                  fontSize: 13,
                  background: C.surface,
                  outline: 'none',
                }}
              >
                {PROFILES.map((p) => (
                  <option key={p} value={p}>{p || 'Default'}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Source
              </label>
              <input
                value={source}
                onChange={(e) => setSource(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 8px',
                  border: `1px solid ${C.border}`,
                  borderRadius: 6,
                  fontSize: 13,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Tags <span style={{ fontWeight: 400 }}>(comma-separated)</span>
            </label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g. homelab, ci, urgent"
              style={{
                width: '100%',
                padding: '6px 8px',
                border: `1px solid ${C.border}`,
                borderRadius: 6,
                fontSize: 13,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {error && (
            <div style={{ marginTop: 10, padding: '6px 10px', background: C.failedBg, border: `1px solid ${C.failed}`, borderRadius: 4, fontSize: 12, color: C.failed }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '7px 16px',
                border: `1px solid ${C.border}`,
                borderRadius: 6,
                background: 'transparent',
                fontSize: 13,
                cursor: 'pointer',
                color: C.text,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !task.trim()}
              style={{
                padding: '7px 16px',
                border: 'none',
                borderRadius: 6,
                background: loading || !task.trim() ? '#93c5fd' : C.accent,
                color: '#fff',
                fontSize: 13,
                fontWeight: 600,
                cursor: loading || !task.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Submitting…' : 'Submit'}
            </button>
          </div>
          <div style={{ marginTop: 8, textAlign: 'right', fontSize: 11, color: C.muted }}>
            <Kbd>⌘</Kbd>+<Kbd>↵</Kbd> to submit
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── HelpOverlay ──────────────────────────────────────────────────────────────
function HelpOverlay({ onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape' || e.key === '?') onClose(); }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const shortcuts = [
    { key: 'j / ↓', desc: 'Move selection down' },
    { key: 'k / ↑', desc: 'Move selection up' },
    { key: 'n', desc: 'New job' },
    { key: 'c', desc: 'Cancel selected job' },
    { key: 'e', desc: 'Dismiss selected job from list' },
    { key: 'f', desc: 'Follow-on job (pre-fill from selected)' },
    { key: '1–6', desc: 'Switch filter tab (All, Pending, Running, Succeeded, Failed, Cancelled)' },
    { key: '?', desc: 'Toggle this help' },
    { key: 'Esc', desc: 'Close modal or help' },
  ];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.3)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: C.surface,
          borderRadius: 10,
          padding: 24,
          width: 400,
          maxWidth: '90vw',
          boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Keyboard Shortcuts</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: C.muted }}>×</button>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <tbody>
            {shortcuts.map(({ key, desc }) => (
              <tr key={key} style={{ borderBottom: `1px solid ${C.border}` }}>
                <td style={{ padding: '7px 0', width: '35%' }}>
                  {key.split('/').map((k, i) => (
                    <span key={i}>{i > 0 && <span style={{ color: C.muted }}> / </span>}<Kbd>{k.trim()}</Kbd></span>
                  ))}
                </td>
                <td style={{ padding: '7px 0', color: C.muted }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('');
  const [activeTag, setActiveTag] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [dismissed, setDismissed] = useState(new Set());
  const [showSubmit, setShowSubmit] = useState(false);
  const [followOnJob, setFollowOnJob] = useState(null);
  const [showHelp, setShowHelp] = useState(false);

  // Resizable sidebar
  const [sidebarWidth, setSidebarWidth] = useState(420);
  const dragging = useRef(false);
  const dragStart = useRef(0);
  const dragWidth = useRef(420);

  // Fetch jobs
  const refresh = useCallback(async () => {
    try {
      const data = await listJobs({ status: tab || undefined, tags: activeTag || undefined, limit: 50 });
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tab, activeTag]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  // Compute stats from job list
  const stats = useMemo(() => {
    const counts = { running: 0, pending: 0, succeeded: 0, failed: 0, cancelled: 0 };
    for (const j of jobs) counts[j.status] = (counts[j.status] || 0) + 1;
    return counts;
  }, [jobs]);

  // Visible (non-dismissed) jobs
  const visibleJobs = useMemo(() => jobs.filter((j) => !dismissed.has(j.id)), [jobs, dismissed]);

  // Selected index among visible jobs
  const selectedIndex = useMemo(() => visibleJobs.findIndex((j) => j.id === selectedId), [visibleJobs, selectedId]);

  // Keyboard navigation
  useEffect(() => {
    function onKey(e) {
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.key === '?' && !showSubmit) { setShowHelp((h) => !h); return; }
      if (showHelp || showSubmit) return;

      if (e.key === 'n') { setShowSubmit(true); setFollowOnJob(null); return; }

      // Tab switching: 1-6
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= TABS.length) { setTab(TABS[num - 1].key); return; }

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        const next = Math.min(selectedIndex + 1, visibleJobs.length - 1);
        if (next >= 0) setSelectedId(visibleJobs[next].id);
        return;
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = Math.max(selectedIndex - 1, 0);
        if (prev >= 0 && visibleJobs.length > 0) setSelectedId(visibleJobs[prev].id);
        return;
      }

      const selJob = visibleJobs[selectedIndex];
      if (!selJob) return;

      if (e.key === 'e') {
        setDismissed((d) => new Set([...d, selJob.id]));
        // Move selection to next
        const next = visibleJobs[selectedIndex + 1] || visibleJobs[selectedIndex - 1];
        setSelectedId(next ? next.id : null);
        return;
      }
      if (e.key === 'c' && (selJob.status === 'pending' || selJob.status === 'running')) {
        cancelJob(selJob.id).then(refresh);
        return;
      }
      if (e.key === 'f') {
        setFollowOnJob(selJob);
        setShowSubmit(true);
        return;
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [visibleJobs, selectedIndex, showSubmit, showHelp, refresh]);

  // Drag to resize sidebar
  function onMouseDown(e) {
    dragging.current = true;
    dragStart.current = e.clientX;
    dragWidth.current = sidebarWidth;
    e.preventDefault();
  }

  useEffect(() => {
    function onMouseMove(e) {
      if (!dragging.current) return;
      const delta = dragStart.current - e.clientX;
      const newW = Math.max(300, Math.min(660, dragWidth.current + delta));
      setSidebarWidth(newW);
    }
    function onMouseUp() { dragging.current = false; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  function handleSubmitted(job) {
    setShowSubmit(false);
    setFollowOnJob(null);
    setSelectedId(job.id);
    refresh();
  }

  function buildFollowOnTask(job) {
    const tail = '';  // output would come from getJobOutput, but we keep it simple for follow-on prefill
    return `Follow-on from job ${job.id.slice(0, 10)}:\n\n${job.task}${tail ? '\n\nPrevious output summary:\n' + tail.slice(-500) : ''}`;
  }

  return (
    <>
      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: ${C.bg}; }
        @keyframes ripple {
          0% { transform: scale(0.8); opacity: 0.5; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #ccc; border-radius: 3px; }
      `}</style>

      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: '10px 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: C.text }}>Agent Orchestrator</span>
            <div style={{ display: 'flex', gap: 8, fontSize: 12, color: C.muted }}>
              {stats.running > 0 && (
                <span style={{ color: C.running, fontWeight: 600 }}>↻ {stats.running} running</span>
              )}
              {stats.pending > 0 && (
                <span style={{ color: C.pending }}>⏳ {stats.pending} pending</span>
              )}
              <span>{total} total</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {error && <span style={{ fontSize: 11, color: C.failed }}>⚠ {error}</span>}
            <button
              onClick={() => setShowHelp(true)}
              style={{ background: 'none', border: `1px solid ${C.border}`, borderRadius: 4, padding: '3px 8px', fontSize: 12, cursor: 'pointer', color: C.muted }}
            >
              ?
            </button>
            <button
              onClick={() => { setShowSubmit(true); setFollowOnJob(null); }}
              style={{
                padding: '5px 14px',
                border: 'none',
                borderRadius: 6,
                background: C.accent,
                color: '#fff',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              + New Job
            </button>
          </div>
        </div>

        {/* Filter tabs + tag dropdown */}
        <div style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: '0 18px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', gap: 0 }}>
            {TABS.map((t, i) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                style={{
                  padding: '8px 14px',
                  border: 'none',
                  borderBottom: `2px solid ${tab === t.key ? C.accent : 'transparent'}`,
                  background: 'transparent',
                  color: tab === t.key ? C.accent : C.muted,
                  fontSize: 13,
                  fontWeight: tab === t.key ? 600 : 400,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
                title={`${i + 1}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <TagDropdown jobs={jobs} activeTag={activeTag} onSelect={setActiveTag} />
          </div>
        </div>

        {/* Main split view */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Job list */}
          <div style={{ flex: 1, overflow: 'auto', minWidth: 280 }}>
            {loading && jobs.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: C.muted, fontSize: 13 }}>Loading…</div>
            )}
            {!loading && visibleJobs.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: C.muted, fontSize: 13 }}>
                No jobs{tab ? ` with status "${tab}"` : ''}
                {activeTag ? ` tagged "${activeTag}"` : ''}
              </div>
            )}
            {visibleJobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selected={job.id === selectedId}
                dismissed={dismissed.has(job.id)}
                onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
              />
            ))}
          </div>

          {/* Drag handle */}
          <div
            onMouseDown={onMouseDown}
            style={{
              width: 5,
              cursor: 'col-resize',
              background: C.border,
              flexShrink: 0,
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = C.borderHover}
            onMouseLeave={(e) => e.currentTarget.style.background = C.border}
          />

          {/* Detail pane */}
          <div style={{ width: sidebarWidth, flexShrink: 0, overflow: 'hidden', background: C.surface, borderLeft: `1px solid ${C.border}` }}>
            <Detail
              jobId={selectedId}
              jobs={jobs}
              onCancel={refresh}
              onDismiss={(id) => {
                setDismissed((d) => new Set([...d, id]));
                setSelectedId(null);
              }}
              onFollowOn={(job) => {
                setFollowOnJob(job);
                setShowSubmit(true);
              }}
            />
          </div>
        </div>
      </div>

      {showSubmit && (
        <SubmitModal
          initialTask={followOnJob ? buildFollowOnTask(followOnJob) : ''}
          initialTags={followOnJob ? (followOnJob.tags || []).join(', ') : ''}
          onClose={() => { setShowSubmit(false); setFollowOnJob(null); }}
          onSubmitted={handleSubmitted}
        />
      )}

      {showHelp && <HelpOverlay onClose={() => setShowHelp(false)} />}
    </>
  );
}

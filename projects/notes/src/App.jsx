import { useState, useEffect, useRef, useCallback } from "react";
import "./reset.css";
import "./app.css";

const EVENTS = [
  { time: "09:00", title: "Standup", meta: "Daily" },
  { time: "10:30", title: "1:1 w/ Manager", meta: "Recurring" },
  { time: "14:00", title: "Infra Review", meta: "Platform" },
];

const LINKS = [
  { label: "ArgoCD", url: "#" },
  { label: "Grafana", url: "#" },
  { label: "SigNoz", url: "#" },
  { label: "BuildBuddy", url: "#" },
  { label: "Notion", url: "#" },
  { label: "GitHub", url: "#" },
];

const INITIAL_TODOS = [
  { id: 1, text: "Ship Envoy Gateway ADR", done: false, scope: "week" },
  { id: 2, text: "Review PR #913 patrol loop fix", done: true, scope: "day" },
  {
    id: 3,
    text: "SQLMesh CI pipeline — test bot integration",
    done: false,
    scope: "day",
  },
  { id: 4, text: "Prep Dr. Claude session slides", done: false, scope: "week" },
  { id: 5, text: "Bosun: fan-out viz edge cases", done: false, scope: "day" },
  { id: 6, text: "Snowflake scope doc feedback", done: false, scope: "week" },
];

function formatDate() {
  return new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatTime() {
  return new Date().toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function useCurrentTime() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  return now;
}

function Capture() {
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  const submit = useCallback(() => {
    if (!note.trim()) return;
    setSent(true);
    setTimeout(() => {
      setNote("");
      setSent(false);
      ref.current?.focus();
    }, 500);
  }, [note]);

  const onKeyDown = useCallback(
    (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  return (
    <section className="capture">
      <textarea
        ref={ref}
        className={`capture-input ${sent ? "capture-input--sent" : ""}`}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="write something..."
        spellCheck={false}
        aria-label="Quick note"
      />
      <footer className="capture-footer">
        <span className="capture-hint">
          {sent ? "sent" : note.trim() ? "\u2318 enter" : "\u00a0"}
        </span>
        {note.length > 0 && (
          <span className="capture-count">{note.length}</span>
        )}
      </footer>
    </section>
  );
}

function isPast(timeStr, now) {
  const [h, m] = timeStr.split(":").map(Number);
  return now.getHours() > h || (now.getHours() === h && now.getMinutes() >= m);
}

function Schedule({ now }) {
  return (
    <section className="panel-section">
      <h2 className="section-label">today</h2>
      <ul className="event-list">
        {EVENTS.map((ev, i) => (
          <li
            key={i}
            className={`event-row ${isPast(ev.time, now) ? "event-row--past" : ""}`}
          >
            <span className="event-time">{ev.time}</span>
            <span className="event-title">{ev.title}</span>
            <span className="event-meta">{ev.meta}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Links() {
  const columns = 3;
  return (
    <section className="panel-section">
      <h2 className="section-label">links</h2>
      <div
        className="links-grid"
        style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}
      >
        {LINKS.map((lk, i) => (
          <a key={i} href={lk.url} className="link">
            {lk.label}
          </a>
        ))}
      </div>
    </section>
  );
}

function Todos() {
  const [scope, setScope] = useState("day");
  const [todos, setTodos] = useState(INITIAL_TODOS);

  const toggle = useCallback((id) => {
    setTodos((prev) =>
      prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)),
    );
  }, []);

  const filtered = todos.filter((t) => t.scope === scope);

  return (
    <section className="panel-section">
      <div className="todo-header">
        <button
          className={`scope-btn ${scope === "day" ? "scope-btn--active" : ""}`}
          onClick={() => setScope("day")}
        >
          today
        </button>
        <button
          className={`scope-btn ${scope === "week" ? "scope-btn--active" : ""}`}
          onClick={() => setScope("week")}
        >
          this week
        </button>
      </div>
      <ul className="todo-list">
        {filtered.map((todo) => (
          <li
            key={todo.id}
            className={`todo-row ${todo.done ? "todo-row--done" : ""}`}
            onClick={() => toggle(todo.id)}
            role="checkbox"
            aria-checked={todo.done}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                toggle(todo.id);
              }
            }}
          >
            <span className="todo-check" aria-hidden="true" />
            <span className="todo-text">{todo.text}</span>
          </li>
        ))}
        {filtered.length === 0 && <li className="todo-empty">nothing here</li>}
      </ul>
    </section>
  );
}

export default function App() {
  const now = useCurrentTime();

  return (
    <div className="root">
      <Capture />
      <div className="divider" aria-hidden="true" />
      <aside className="panel">
        <header className="panel-header">
          <span className="date">{formatDate()}</span>
          <span className="clock">
            {now.toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </header>
        <Schedule now={now} />
        <Links />
        <Todos />
      </aside>
    </div>
  );
}

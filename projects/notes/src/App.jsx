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

const EMPTY_TODOS = {
  goal: "",
  daily: ["", "", ""],
  goalDone: false,
  dailyDone: [false, false, false],
};

const MOCK_TODOS = {
  goal: "Ship Envoy Gateway ADR",
  daily: [
    "Review PR #913 patrol loop fix",
    "SQLMesh CI pipeline — test bot",
    "Bosun: fan-out viz edge cases",
  ],
  goalDone: false,
  dailyDone: [true, false, false],
};

const TZ = "America/Vancouver";

function getTodayKey() {
  return new Date().toLocaleDateString("en-CA", { timeZone: TZ });
}

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
  const [todos, setTodos] = useState(MOCK_TODOS);
  const [editing, setEditing] = useState(false);
  const [dateKey, setDateKey] = useState(getTodayKey);
  const goalRef = useRef(null);
  const dailyRefs = useRef([null, null, null]);

  // Reset daily at midnight Vancouver time
  useEffect(() => {
    const check = setInterval(() => {
      const now = getTodayKey();
      if (now !== dateKey) {
        setDateKey(now);
        setTodos((prev) => ({
          ...prev,
          daily: ["", "", ""],
          dailyDone: [false, false, false],
        }));
      }
    }, 30_000);
    return () => clearInterval(check);
  }, [dateKey]);

  const setGoal = (text) => setTodos((prev) => ({ ...prev, goal: text }));
  const toggleGoal = () =>
    setTodos((prev) => ({ ...prev, goalDone: !prev.goalDone }));

  const setDailyText = (i, text) =>
    setTodos((prev) => ({
      ...prev,
      daily: prev.daily.map((d, j) => (j === i ? text : d)),
    }));

  const toggleDaily = (i) =>
    setTodos((prev) => ({
      ...prev,
      dailyDone: prev.dailyDone.map((d, j) => (j === i ? !d : d)),
    }));

  const startEditing = () => {
    setEditing(true);
    setTimeout(() => goalRef.current?.focus(), 0);
  };

  const handleKeyDown = (e, nextRef) => {
    if (e.key === "Enter") {
      e.preventDefault();
      nextRef?.focus();
    }
    if (e.key === "Escape") {
      setEditing(false);
    }
  };

  return (
    <section className="panel-section">
      <h2
        className="section-label section-label--interactive"
        onClick={editing ? () => setEditing(false) : startEditing}
      >
        {editing ? "done" : "todo"}
      </h2>

      {/* Weekly goal — always an input */}
      <input
        ref={goalRef}
        className={`todo-field todo-field--goal ${todos.goalDone && !editing ? "todo-field--done" : ""} ${!todos.goal && !editing ? "todo-field--empty" : ""}`}
        value={editing ? todos.goal : todos.goal || "set weekly goal"}
        readOnly={!editing}
        onChange={(e) => setGoal(e.target.value)}
        onClick={
          !editing && todos.goal
            ? toggleGoal
            : !editing
              ? startEditing
              : undefined
        }
        onKeyDown={
          editing
            ? (e) => handleKeyDown(e, dailyRefs.current[0])
            : (e) => {
                if (e.key === " " || e.key === "Enter") {
                  e.preventDefault();
                  todos.goal ? toggleGoal() : startEditing();
                }
              }
        }
        placeholder="weekly goal"
        spellCheck={false}
        tabIndex={0}
      />

      {/* 3 daily goals — always inputs */}
      {todos.daily.map((text, i) => {
        const allDailyEmpty = !editing && todos.daily.every((d) => !d);
        const emptyLabel =
          allDailyEmpty && i === 0 && todos.goal ? "set daily goals" : "...";

        return (
          <div key={i} className="todo-daily-row">
            <span
              className={`todo-dash ${!text && !editing ? "todo-dash--empty" : ""}`}
            >
              –
            </span>
            <input
              ref={(el) => (dailyRefs.current[i] = el)}
              className={`todo-field ${todos.dailyDone[i] && !editing ? "todo-field--done" : ""} ${!text && !editing ? "todo-field--empty" : ""}`}
              value={editing ? text : text || emptyLabel}
              readOnly={!editing}
              onChange={(e) => setDailyText(i, e.target.value)}
              onClick={
                !editing && text
                  ? () => toggleDaily(i)
                  : !editing
                    ? startEditing
                    : undefined
              }
              onKeyDown={
                editing
                  ? (e) => handleKeyDown(e, dailyRefs.current[i + 1] || null)
                  : (e) => {
                      if (e.key === " " || e.key === "Enter") {
                        e.preventDefault();
                        text ? toggleDaily(i) : startEditing();
                      }
                    }
              }
              placeholder="daily goal"
              spellCheck={false}
              tabIndex={0}
            />
          </div>
        );
      })}
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

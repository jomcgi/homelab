import { useState, useRef, useCallback, useMemo } from "react";
import {
  CONDITIONS,
  CONDITION_STYLES,
  INFERENCE_URL,
  INFERENCE_MODEL,
  buildPipelineSchema,
  buildSystemPrompt,
} from "./pipeline-config.js";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function extractPromptText(el) {
  const parts = [];
  el.childNodes.forEach((n) => {
    if (n.nodeType === 3) parts.push(n.textContent);
    else if (n.dataset?.type) parts.push(`@${n.dataset.type}:${n.dataset.id}`);
    else parts.push(n.textContent);
  });
  return parts
    .join("")
    .replace(/\u00A0/g, " ")
    .trim();
}

// ─── Inference ───────────────────────────────────────────────────────────────

async function inferPipeline(prompt, agents) {
  const res = await fetch(INFERENCE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: INFERENCE_MODEL,
      messages: [
        { role: "system", content: buildSystemPrompt(agents) },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
      max_tokens: 800,
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "pipeline",
          strict: true,
          schema: buildPipelineSchema(agents),
        },
      },
    }),
  });

  if (!res.ok) throw new Error(`Inference failed: ${res.status}`);

  const data = await res.json();
  const text =
    data.choices?.[0]?.message?.content ||
    data.content?.find((b) => b.type === "text")?.text ||
    "";
  const clean = text.replace(/```json|```/g, "").trim();
  const parsed = JSON.parse(clean);

  if (!parsed.steps?.length) throw new Error("Empty pipeline");

  return parsed.steps.map((s, i) => ({
    agent: s.agent,
    task: s.task || "",
    condition: i === 0 ? "always" : s.condition || "always",
  }));
}

// ─── @-mention categories (built from props) ────────────────────────────────

const CATEGORY_STYLES = {
  analyse: {
    label: "Analyse",
    icon: "🔬",
    bg: "#dbeafe",
    fg: "#1e40af",
    pillCls: "pill-analyse",
  },
  action: {
    label: "Action",
    icon: "🔧",
    bg: "#fef3c7",
    fg: "#92400e",
    pillCls: "pill-action",
  },
  validate: {
    label: "Validate",
    icon: "✓",
    bg: "#d1fae5",
    fg: "#065f46",
    pillCls: "pill-validate",
  },
  tool: {
    label: "Tool",
    icon: "⚙",
    bg: "#f3e8ff",
    fg: "#6b21a8",
    pillCls: "pill-tool",
  },
};

function buildMentionCats(agents) {
  const grouped = {};
  for (const a of agents) {
    const cat = a.category || "action";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push({ id: a.id, meta: a.desc || "" });
  }
  const cats = {};
  for (const [key, items] of Object.entries(grouped)) {
    const style = CATEGORY_STYLES[key] || CATEGORY_STYLES.action;
    cats[key] = { ...style, items };
  }
  return cats;
}

// ─── Condition select ────────────────────────────────────────────────────────

function ConditionSelect({ value, onChange }) {
  const style = CONDITION_STYLES[value] || CONDITION_STYLES["always"];
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        fontSize: 10,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 10,
        border: `0.5px solid ${style.border}`,
        color: style.color,
        background: style.bg,
        cursor: "pointer",
        fontFamily: "inherit",
        outline: "none",
        WebkitAppearance: "none",
        textAlign: "center",
      }}
    >
      {CONDITIONS.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}

// ─── Connector ───────────────────────────────────────────────────────────────

function Connector({ condition, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0,
        padding: "2px 0",
      }}
    >
      <div
        style={{
          width: 0.5,
          height: 12,
          background: "var(--color-border-secondary, #d1d5db)",
        }}
      />
      <ConditionSelect value={condition} onChange={onChange} />
      <div
        style={{
          width: 0.5,
          height: 12,
          background: "var(--color-border-secondary, #d1d5db)",
        }}
      />
    </div>
  );
}

// ─── Step card ───────────────────────────────────────────────────────────────

function StepCard({
  step,
  index,
  agents,
  onUpdateTask,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
  isDragging,
}) {
  const ag = agents.find((a) => a.id === step.agent) || {
    id: step.agent,
    label: step.agent,
    icon: "◆",
    bg: "#f3f4f6",
    fg: "#374151",
  };
  const taskRef = useRef(null);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        onDragStart(index);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver(index);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop(index);
      }}
      style={{
        width: "100%",
        background: "#fff",
        border: "0.5px solid #e5e7eb",
        borderRadius: 12,
        overflow: "hidden",
        opacity: isDragging ? 0.35 : 1,
        transition: "border-color 0.15s, opacity 0.15s",
        position: "relative",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#d1d5db")}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#e5e7eb")}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 14px",
          cursor: "grab",
        }}
      >
        <span
          style={{
            color: "#d1d5db",
            fontSize: 14,
            opacity: 0.6,
            lineHeight: 1,
            letterSpacing: -1,
            userSelect: "none",
          }}
        >
          ⠿
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: 12,
            fontWeight: 500,
            color: "#374151",
          }}
        >
          <span
            style={{
              width: 20,
              height: 20,
              borderRadius: 5,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 10,
              background: ag.bg,
              color: ag.fg,
              flexShrink: 0,
            }}
          >
            {ag.icon}
          </span>
          {ag.label}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 11,
            color: "#d1d5db",
            fontFamily: "monospace",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {index + 1}
        </span>
        <button
          onClick={() => onRemove(index)}
          style={{
            fontSize: 14,
            color: "#d1d5db",
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 0,
            fontFamily: "inherit",
            transition: "color 0.12s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#d1d5db")}
        >
          ×
        </button>
      </div>

      {/* Task */}
      <div
        ref={taskRef}
        contentEditable
        suppressContentEditableWarning
        onInput={() => onUpdateTask(index, taskRef.current?.textContent || "")}
        onMouseDown={(e) => e.stopPropagation()}
        data-placeholder="Describe what this step should do…"
        style={{
          borderTop: "0.5px solid #f3f4f6",
          padding: "8px 14px 10px",
          fontSize: 12.5,
          lineHeight: 1.6,
          color: "#6b7280",
          outline: "none",
          minHeight: 36,
        }}
      >
        {step.task}
      </div>
    </div>
  );
}

// ─── Composer (with @-mention) ───────────────────────────────────────────────

function Composer({ onInfer, inferring, mentionCats }) {
  const editorRef = useRef(null);
  const [focused, setFocused] = useState(false);
  const [hasText, setHasText] = useState(false);
  const [ddState, setDdState] = useState({ mode: "closed", sel: 0 });
  const atRef = useRef({ node: null, offset: 0 });

  const closeDd = useCallback(() => {
    setDdState({ mode: "closed", sel: 0 });
    atRef.current = { node: null, offset: 0 };
  }, []);

  const insertMention = useCallback(
    (catKey, item) => {
      const cat = mentionCats[catKey];
      const { node, offset } = atRef.current;
      if (!node) {
        closeDd();
        return;
      }

      const sel = window.getSelection();
      const range = document.createRange();
      range.setStart(node, offset - 1);
      range.setEndAfter(node);
      range.deleteContents();

      const pill = document.createElement("span");
      pill.className = `pill ${cat.pillCls}`;
      pill.contentEditable = "false";
      pill.dataset.type = catKey;
      pill.dataset.id = item.id;
      pill.style.cssText =
        "display:inline-flex;align-items:center;gap:3px;border-radius:5px;padding:1px 7px;font-size:11px;font-weight:500;white-space:nowrap;vertical-align:middle;position:relative;top:-1px;";
      pill.style.background = cat.bg;
      pill.style.color = cat.fg;

      const iconSpan = document.createElement("span");
      iconSpan.style.cssText = "font-size:9px;opacity:.7";
      iconSpan.textContent = cat.icon;
      pill.appendChild(iconSpan);
      pill.appendChild(document.createTextNode(item.id));

      const spacer = document.createTextNode("\u00A0");
      range.insertNode(spacer);
      range.insertNode(pill);

      const newRange = document.createRange();
      newRange.setStartAfter(spacer);
      newRange.collapse(true);
      sel.removeAllRanges();
      sel.addRange(newRange);

      closeDd();
      setHasText(true);
    },
    [closeDd, mentionCats],
  );

  const handleInput = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    setHasText(el.textContent.trim().length > 0);

    const sel = window.getSelection();
    if (!sel?.rangeCount) {
      closeDd();
      return;
    }
    const range = sel.getRangeAt(0);
    const node = range.startContainer;
    const off = range.startOffset;

    if (node.nodeType === 3) {
      const txt = node.textContent.substring(0, off);
      const ai = txt.lastIndexOf("@");
      if (ai !== -1 && txt.slice(ai) === "@") {
        atRef.current = { node, offset: off };
        setDdState({ mode: "cats", sel: 0 });
      } else if (ddState.mode !== "closed") {
        if (ai === -1) closeDd();
      }
    } else if (ddState.mode !== "closed") {
      closeDd();
    }
  }, [ddState.mode, closeDd]);

  const handleKeyDown = useCallback(
    (e) => {
      if (ddState.mode === "closed") {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          const text = extractPromptText(editorRef.current);
          if (text) onInfer(text);
        }
        return;
      }

      const cats = Object.keys(mentionCats);
      const items =
        ddState.mode === "cats" ? cats : mentionCats[ddState.mode]?.items || [];

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setDdState((s) => ({ ...s, sel: (s.sel + 1) % items.length }));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setDdState((s) => ({
          ...s,
          sel: (s.sel - 1 + items.length) % items.length,
        }));
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (ddState.mode === "cats") {
          setDdState({ mode: cats[ddState.sel], sel: 0 });
        } else {
          insertMention(ddState.mode, items[ddState.sel]);
        }
      } else if (e.key === "Escape") {
        ddState.mode !== "cats"
          ? setDdState({ mode: "cats", sel: 0 })
          : closeDd();
      } else if (e.key === "Backspace") {
        closeDd();
      }
    },
    [ddState, onInfer, insertMention, closeDd, mentionCats],
  );

  // ── Dropdown render ──────────────────────────────────────────────────────
  const ddItems =
    ddState.mode === "cats"
      ? Object.entries(mentionCats).map(([k, cat]) => ({
          key: k,
          icon: cat.icon,
          bg: cat.bg,
          fg: cat.fg,
          label: cat.label.toLowerCase(),
          chevron: true,
        }))
      : (mentionCats[ddState.mode]?.items || []).map((item) => ({
          key: item.id,
          icon: mentionCats[ddState.mode].icon,
          bg: mentionCats[ddState.mode].bg,
          fg: mentionCats[ddState.mode].fg,
          label: item.id,
          meta: item.meta,
        }));

  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          borderRadius: 12,
          border: `0.5px solid ${focused ? "#d1d5db" : "#e5e7eb"}`,
          background: "#fff",
          transition: "border-color 0.2s, box-shadow 0.2s",
          boxShadow: focused ? "0 4px 16px rgba(0,0,0,0.07)" : "none",
        }}
      >
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            setTimeout(closeDd, 150);
          }}
          data-placeholder="Describe the pipeline… type @ to mention agents or profiles"
          style={{
            minHeight: 80,
            maxHeight: 200,
            overflowY: "auto",
            padding: "14px 16px 8px",
            fontSize: 13.5,
            lineHeight: 1.7,
            color: "#1f2937",
            outline: "none",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderTop: "0.5px solid #f3f4f6",
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "#d1d5db",
              fontFamily: "monospace",
            }}
          >
            @ to mention
          </span>

          <span style={{ marginLeft: "auto", fontSize: 11, color: "#d1d5db" }}>
            {navigator.platform?.includes("Mac") ? "⌘↵" : "Ctrl+↵"}
          </span>

          <button
            onClick={() => {
              const text = extractPromptText(editorRef.current);
              if (text) onInfer(text);
            }}
            disabled={!hasText || inferring}
            style={{
              fontSize: 11.5,
              fontWeight: 500,
              padding: "5px 14px",
              background: "#111827",
              color: "#fff",
              borderRadius: 7,
              border: "none",
              cursor: !hasText || inferring ? "not-allowed" : "pointer",
              opacity: !hasText || inferring ? 0.2 : 1,
              transition: "opacity 0.15s",
              fontFamily: "inherit",
            }}
          >
            {inferring ? "Inferring…" : "Infer pipeline"}
          </button>
        </div>
      </div>

      {/* Dropdown */}
      {ddState.mode !== "closed" && (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: "100%",
            marginTop: 6,
            width: 230,
            background: "#fff",
            border: "0.5px solid #e5e7eb",
            borderRadius: 10,
            boxShadow: "0 8px 28px rgba(0,0,0,0.12)",
            overflow: "hidden",
            zIndex: 10,
            padding: "4px 0",
          }}
        >
          {ddState.mode !== "cats" && (
            <div
              onClick={() => setDdState({ mode: "cats", sel: 0 })}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 11px",
                fontSize: 11.5,
                color: "#6b7280",
                cursor: "pointer",
                borderBottom: "0.5px solid #f3f4f6",
              }}
            >
              <span>‹</span>
              <span style={{ fontWeight: 500, color: "#374151" }}>
                {mentionCats[ddState.mode]?.label}
              </span>
            </div>
          )}

          {ddItems.map((item, i) => (
            <div
              key={item.key}
              onMouseDown={(e) => {
                e.preventDefault();
                if (ddState.mode === "cats") {
                  setDdState({ mode: item.key, sel: 0 });
                } else {
                  insertMention(
                    ddState.mode,
                    mentionCats[ddState.mode].items[i],
                  );
                }
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "7px 11px",
                cursor: "pointer",
                fontSize: 12.5,
                color: "#374151",
                background: i === ddState.sel ? "#f9fafb" : "transparent",
                transition: "background 0.08s",
              }}
            >
              <span
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  background: item.bg,
                  color: item.fg,
                  flexShrink: 0,
                }}
              >
                {item.icon}
              </span>
              <span>{item.label}</span>
              {item.meta && (
                <span
                  style={{
                    fontSize: 11,
                    color: "#d1d5db",
                    marginLeft: "auto",
                  }}
                >
                  {item.meta}
                </span>
              )}
              {item.chevron && (
                <span
                  style={{
                    fontSize: 11,
                    color: "#d1d5db",
                    marginLeft: "auto",
                  }}
                >
                  ›
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── PipelineComposer (main export) ──────────────────────────────────────────

export default function PipelineComposer({ agents, onSubmit }) {
  const [pipeline, setPipeline] = useState([]);
  const [inferring, setInferring] = useState(false);
  const [inferSource, setInferSource] = useState(null); // "inferred" | "manual" | null
  const [submitting, setSubmitting] = useState(false);
  const dragRef = useRef(null);

  const mentionCats = useMemo(() => buildMentionCats(agents), [agents]);

  // ── Inference ────────────────────────────────────────────────────────────
  const handleInfer = useCallback(
    async (prompt) => {
      setInferring(true);
      try {
        const steps = await inferPipeline(prompt, agents);
        setPipeline(steps);
        setInferSource("inferred");
      } catch (err) {
        console.error("Pipeline inference failed:", err);
        setInferSource("manual");
      } finally {
        setInferring(false);
      }
    },
    [agents],
  );

  // ── Pipeline mutations ───────────────────────────────────────────────────
  const updateTask = useCallback((idx, task) => {
    setPipeline((p) => p.map((s, i) => (i === idx ? { ...s, task } : s)));
  }, []);

  const updateCondition = useCallback((idx, condition) => {
    setPipeline((p) => p.map((s, i) => (i === idx ? { ...s, condition } : s)));
  }, []);

  const removeStep = useCallback((idx) => {
    setPipeline((p) => {
      const next = p.filter((_, i) => i !== idx);
      if (idx === 0 && next.length > 0) {
        next[0] = { ...next[0], condition: "always" };
      }
      return next;
    });
  }, []);

  const addStep = useCallback((agentId) => {
    setPipeline((p) => [
      ...p,
      { agent: agentId, task: "", condition: "always" },
    ]);
    setInferSource((s) => s || "manual");
  }, []);

  // ── Drag and drop ────────────────────────────────────────────────────────
  const handleDragStart = useCallback((idx) => {
    dragRef.current = idx;
  }, []);

  const handleDragOver = useCallback(() => {}, []);

  const handleDrop = useCallback((targetIdx) => {
    const fromIdx = dragRef.current;
    if (fromIdx == null || fromIdx === targetIdx) return;
    setPipeline((p) => {
      const next = [...p];
      const [item] = next.splice(fromIdx, 1);
      next.splice(targetIdx, 0, item);
      next[0] = { ...next[0], condition: "always" };
      return next;
    });
    dragRef.current = null;
  }, []);

  // ── Submit ───────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!pipeline.length || submitting) return;
    setSubmitting(true);
    try {
      const spec = {
        steps: pipeline.map((s, i) => ({
          agent: s.agent,
          task: s.task || "(no task)",
          condition: i === 0 ? "always" : s.condition,
        })),
      };
      await onSubmit?.(spec);
    } finally {
      setSubmitting(false);
    }
  }, [pipeline, submitting, onSubmit]);

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div>
      {/* Phase 1: Composer */}
      <Label>Task prompt</Label>
      <Composer
        onInfer={handleInfer}
        inferring={inferring}
        mentionCats={mentionCats}
      />

      {/* Phase 2: Pipeline editor (always visible) */}
      <div style={{ marginTop: 24 }}>
        <Label>
          Agent pipeline
          {inferSource && (
            <span
              style={{
                fontWeight: 400,
                textTransform: "none",
                letterSpacing: 0,
                fontSize: 10,
                marginLeft: 4,
                opacity: 0.6,
              }}
            >
              ·{" "}
              {inferSource === "inferred"
                ? "inferred from prompt"
                : "build manually"}
            </span>
          )}
        </Label>

        {pipeline.length === 0 ? (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              fontSize: 12.5,
              color: "#d1d5db",
              background: "#f9fafb",
              borderRadius: 12,
              border: "0.5px dashed #e5e7eb",
            }}
          >
            {inferring
              ? "Inferring pipeline from prompt…"
              : "Write a task above and infer, or add agents manually below"}
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 0,
            }}
          >
            {pipeline.map((step, idx) => (
              <div key={idx} style={{ width: "100%" }}>
                {idx > 0 && (
                  <Connector
                    condition={step.condition}
                    onChange={(c) => updateCondition(idx, c)}
                  />
                )}
                <StepCard
                  step={step}
                  index={idx}
                  agents={agents}
                  onUpdateTask={updateTask}
                  onRemove={removeStep}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  isDragging={dragRef.current === idx}
                />
              </div>
            ))}
          </div>
        )}

        {/* Actions row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 12,
            padding: "0 4px",
          }}
        >
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) addStep(e.target.value);
              e.target.value = "";
            }}
            style={{
              fontSize: 11.5,
              color: "#9ca3af",
              background: "#f9fafb",
              border: "0.5px solid #e5e7eb",
              borderRadius: 7,
              padding: "5px 8px",
              cursor: "pointer",
              fontFamily: "inherit",
              outline: "none",
            }}
          >
            <option value="">+ add step</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.id}
              </option>
            ))}
          </select>

          {pipeline.length > 0 && (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              style={{
                marginLeft: "auto",
                fontSize: 12,
                fontWeight: 500,
                padding: "6px 16px",
                background: "#111827",
                color: "#fff",
                borderRadius: 8,
                border: "none",
                cursor: submitting ? "not-allowed" : "pointer",
                opacity: submitting ? 0.5 : 1,
                transition: "opacity 0.15s",
                fontFamily: "inherit",
              }}
            >
              {submitting ? "Submitting…" : "Submit to orchestrator"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Tiny label component ────────────────────────────────────────────────────

function Label({ children }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 500,
        textTransform: "uppercase",
        letterSpacing: "0.07em",
        color: "#9ca3af",
        marginBottom: 6,
      }}
    >
      {children}
    </div>
  );
}

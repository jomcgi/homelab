import { C, mono } from "../tokens.js";

export function TodoChecklist({ todos }) {
  if (!todos || todos.length === 0) return null;

  return (
    <div
      style={{
        margin: "8px 0",
        padding: "8px 12px",
        borderLeft: `2px solid ${C.accentBlue}`,
        borderRadius: 4,
      }}
    >
      {todos.map((todo, i) => {
        const status = todo.status || "pending";
        const isCompleted = status === "completed";
        const isInProgress = status === "in_progress";

        return (
          <div
            key={todo.id || i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
              padding: "3px 0",
              fontFamily: mono,
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            {/* Status icon */}
            <span
              style={{
                flexShrink: 0,
                width: 16,
                height: 16,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginTop: 2,
              }}
            >
              {isCompleted ? (
                <span style={{ color: C.success, fontSize: 14 }}>&#x2713;</span>
              ) : isInProgress ? (
                <span style={{ color: C.accentBlue, fontSize: 10 }}>&#x25A0;</span>
              ) : (
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    border: `1.5px solid ${C.textTer}`,
                    display: "inline-block",
                  }}
                />
              )}
            </span>

            {/* Task text */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <span
                style={{
                  color: isCompleted ? C.textTer : isInProgress ? C.text : C.textSec,
                  fontWeight: isInProgress ? 600 : 400,
                  textDecoration: isCompleted ? "line-through" : "none",
                }}
              >
                {todo.subject || todo.content || `Task ${i + 1}`}
              </span>
              {isInProgress && todo.activeForm && (
                <div style={{ fontSize: 11, color: C.accentBlue, marginTop: 1 }}>
                  {todo.activeForm}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

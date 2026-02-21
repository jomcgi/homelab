import { useState } from "react";
import { C } from "@/lib/tokens";

interface ChatInputProps {
  isDM?: boolean;
  onSubmit?: (message: string, channel: string) => void;
}

export function ChatInput({ isDM = false, onSubmit }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [channel, setChannel] = useState("public");

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onSubmit?.(trimmed, channel);
    setInput("");
  };

  return (
    <div style={{ borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
      {channel === "private" && (
        <div
          style={{
            padding: "6px 20px",
            background: C.privateBg,
            fontFamily: C.sans,
            fontSize: 12,
            color: C.private,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          Whispering to: <strong>Vex</strong>
          <button
            onClick={() => setChannel("public")}
            style={{
              marginLeft: "auto",
              fontFamily: C.sans,
              fontSize: 11,
              background: "none",
              border: "none",
              color: C.private,
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Cancel
          </button>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center" }}>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          style={{
            fontFamily: C.sans,
            fontSize: 12,
            padding: "10px 12px",
            background: C.bgMuted,
            color: channel === "private" ? C.private : C.fgMuted,
            border: "none",
            borderRight: `1px solid ${C.border}`,
            cursor: "pointer",
            outline: "none",
          }}
        >
          <option value="public">Public</option>
          <option value="private">Whisper</option>
          {isDM && <option value="narrate">Narrate</option>}
        </select>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder={
            channel === "private"
              ? "Private message..."
              : channel === "narrate"
                ? "Narration (typed)..."
                : "Message the table..."
          }
          style={{
            flex: 1,
            fontFamily: C.sans,
            fontSize: 14,
            padding: "10px 16px",
            background: "transparent",
            color: C.fg,
            border: "none",
            outline: "none",
          }}
        />
      </div>
    </div>
  );
}

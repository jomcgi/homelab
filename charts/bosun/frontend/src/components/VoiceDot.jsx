import { C } from "../tokens.js";

export function VoiceDot({ state, size }) {
  const sz = size || 8;
  const color = state === "speaking" ? C.voice : state === "listening" ? C.success : C.textFaint;
  return (
    <div style={{ position: "relative", width: sz, height: sz, flexShrink: 0 }}>
      <div className="vcc-animated" style={{
        width: sz, height: sz, borderRadius: "50%", backgroundColor: color,
        transition: "background-color 200ms",
        willChange: state !== "off" ? "opacity" : "auto",
        animation: state !== "off" ? "vcc-pulse 2s ease-in-out infinite" : "none",
      }} />
    </div>
  );
}

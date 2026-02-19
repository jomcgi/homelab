import { C, sans, mono } from "../tokens.js";
import { artifactIcon } from "../artifactIcons.js";

export function ArtifactGalleryItem({ artifact, time, onClick }) {
  const Icon = artifactIcon(artifact);

  return (
    <button onClick={onClick} style={{
      display: "flex", flexDirection: "column", alignItems: "stretch",
      border: `1px solid ${C.border}`, borderRadius: 8,
      backgroundColor: C.bg, cursor: "pointer", overflow: "hidden",
      fontFamily: sans, transition: "all 150ms",
      padding: 0,
    }}
    onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.accentBlue; e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.08)"; }}
    onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
    >
      {/* Thumbnail or icon placeholder */}
      {artifact.type === "image" && artifact.data ? (
        <div style={{ height: 80, overflow: "hidden", backgroundColor: C.surface }}>
          <img
            src={`data:${artifact.mimeType || "image/png"};base64,${artifact.data}`}
            alt={artifact.label}
            style={{ width: "100%", height: 80, objectFit: "cover" }}
          />
        </div>
      ) : (
        <div style={{
          height: 80, display: "flex", alignItems: "center", justifyContent: "center",
          backgroundColor: C.surface,
        }}>
          <Icon size={24} color={C.textTer} strokeWidth={1.5} />
        </div>
      )}
      {/* Label + timestamp */}
      <div style={{ padding: "6px 8px" }}>
        <div style={{
          fontSize: 11, color: C.text, fontWeight: 500,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {artifact.label}
        </div>
        {time && (
          <div style={{ fontSize: 10, color: C.textTer, marginTop: 2, fontFamily: mono }}>
            {time}
          </div>
        )}
      </div>
    </button>
  );
}

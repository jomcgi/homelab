import { C, mono } from "../tokens.js";
import { artifactIcon } from "../artifactIcons.js";

export function ArtifactCard({ artifact, onClick, selected }) {
  if (!artifact) return null;
  const Icon = artifactIcon(artifact);
  return (
    <button onClick={onClick} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "5px 10px", borderRadius: 6, cursor: "pointer",
      border: selected ? `1.5px solid ${C.accentBlue}` : `1px solid ${C.border}`,
      backgroundColor: selected ? "#EFF6FF" : C.surface,
      fontFamily: mono, fontSize: 12, color: selected ? C.accentBlue : C.textSec,
      marginTop: 6, marginRight: 6, transition: "all 150ms",
    }}>
      <Icon size={13} />
      <span>{artifact.label}</span>
      {artifact.additions > 0 && <span style={{ color: C.addGreen }}>+{artifact.additions}</span>}
      {artifact.deletions > 0 && <span style={{ color: C.delRed }}>{"-"}{artifact.deletions}</span>}
    </button>
  );
}

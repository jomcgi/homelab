import { FileCode, FileText, Terminal, GitBranch, Image, Search, FolderOpen, Globe, PenLine } from "lucide-react";

// Maps artifact type + toolName to the best icon component.
// Used by ArtifactCard, InlineArtifact, ArtifactGalleryItem, DetailPanel.

const toolIcons = {
  Read: FileText,
  Bash: Terminal,
  Grep: Search,
  Glob: FolderOpen,
  WebFetch: Globe,
  Write: PenLine,
  Edit: PenLine,
};

const typeIcons = {
  diff: FileCode,
  output: Terminal,
  mermaid: GitBranch,
  image: Image,
};

export function artifactIcon(artifact) {
  if (!artifact) return FileCode;
  // Prefer tool-specific icon for output artifacts
  if (artifact.toolName && toolIcons[artifact.toolName]) {
    return toolIcons[artifact.toolName];
  }
  return typeIcons[artifact.type] || FileCode;
}

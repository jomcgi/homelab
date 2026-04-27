// Maps Note.type values to CSS custom-property references defined in
// projects/websites/shared/tokens.css. Unknown types fall through to
// --cluster-other so new types appear in the legend without a code
// change.

export const CLUSTER_COLORS = {
  atom: "var(--cluster-atom)",
  fact: "var(--cluster-atom)", // legacy alias for distilled atoms
  raw: "var(--cluster-raw)",
  gap: "var(--cluster-gap)",
  active: "var(--cluster-active)",
  paper: "var(--cluster-paper)",
};

const FALLBACK = "var(--cluster-other)";

export function colorFor(type) {
  return CLUSTER_COLORS[type] ?? FALLBACK;
}

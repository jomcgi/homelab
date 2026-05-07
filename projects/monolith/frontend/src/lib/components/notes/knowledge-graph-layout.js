// Pure helpers for projecting server-supplied knowledge-graph layout
// (FA2 + post-rescale to ~[-1, +1] in compute_layout) into the
// component's pixel space, plus node-radius scaling. Extracted so the
// arithmetic can be unit-tested without mounting the Svelte component.

/**
 * Compute the visual radius for a node given its degree.
 * baseRadius is the floor; hubBoost scales the log-degree bonus.
 */
export function radiusFor(degree, { baseRadius, hubBoost }) {
  return baseRadius + hubBoost * Math.log2(1 + (degree || 0));
}

/**
 * Project server-supplied (x, y) coords (NetworkX-normalized, ~[-1, +1])
 * into pixel space centred on (cx, cy) with the layout's bounding span
 * scaled to `span` pixels. Falls back to (cx ± jitter, cy ± jitter) when
 * server coords are missing or non-finite (newcomer node, brief gap
 * between gardener add and next layout pass).
 *
 * `rand` defaults to Math.random but is injectable for deterministic
 * tests.
 */
export function projectXY(n, cx, cy, span, rand = Math.random) {
  const sx = Number.isFinite(n.x) ? n.x * span + cx : cx + jitter(rand);
  const sy = Number.isFinite(n.y) ? n.y * span + cy : cy + jitter(rand);
  return [sx, sy];
}

function jitter(rand) {
  return (rand() - 0.5) * 100;
}

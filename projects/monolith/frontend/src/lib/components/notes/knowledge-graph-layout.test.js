import { describe, it, expect } from "vitest";
import { radiusFor, projectXY } from "./knowledge-graph-layout.js";

const CFG = { baseRadius: 2.8, hubBoost: 0.5 };

describe("radiusFor", () => {
  it("returns baseRadius when degree is 0", () => {
    expect(radiusFor(0, CFG)).toBeCloseTo(2.8);
  });

  it("treats null/undefined degree as 0", () => {
    expect(radiusFor(undefined, CFG)).toBeCloseTo(2.8);
    expect(radiusFor(null, CFG)).toBeCloseTo(2.8);
  });

  it("is monotonic in degree", () => {
    const r0 = radiusFor(0, CFG);
    const r1 = radiusFor(1, CFG);
    const r10 = radiusFor(10, CFG);
    expect(r1).toBeGreaterThan(r0);
    expect(r10).toBeGreaterThan(r1);
  });

  it("uses log2(1 + degree) scaling", () => {
    // radiusFor(d) = base + hubBoost * log2(1 + d)
    // For degree=3: base + hubBoost * log2(4) = 2.8 + 0.5 * 2 = 3.8
    expect(radiusFor(3, CFG)).toBeCloseTo(3.8);
  });
});

describe("projectXY", () => {
  const cx = 600;
  const cy = 400;
  const span = 300;

  it("scales server coords from [-1, 1] into pixel space centred on (cx, cy)", () => {
    const [x, y] = projectXY({ x: 0, y: 0 }, cx, cy, span);
    expect(x).toBe(cx);
    expect(y).toBe(cy);
  });

  it("places node at right edge when server x = 1", () => {
    const [x, _] = projectXY({ x: 1, y: 0 }, cx, cy, span);
    expect(x).toBe(cx + span); // 900
  });

  it("places node at top-left when server (x, y) = (-1, -1)", () => {
    const [x, y] = projectXY({ x: -1, y: -1 }, cx, cy, span);
    expect(x).toBe(cx - span);
    expect(y).toBe(cy - span);
  });

  it("falls back to centre + jitter when server x is undefined", () => {
    // Stub rand to return 0.5 → jitter() = 0
    const rand = () => 0.5;
    const [x, y] = projectXY(
      { x: undefined, y: undefined },
      cx,
      cy,
      span,
      rand,
    );
    expect(x).toBe(cx);
    expect(y).toBe(cy);
  });

  it("falls back when server coord is NaN or Infinity", () => {
    const rand = () => 0.5; // jitter = 0
    expect(projectXY({ x: NaN, y: 0 }, cx, cy, span, rand)).toEqual([cx, cy]);
    expect(projectXY({ x: 0, y: Infinity }, cx, cy, span, rand)).toEqual([
      cx,
      cy,
    ]);
  });

  it("fallback positions are bounded by ±50 px around the centre", () => {
    // For any rand in [0, 1): jitter ∈ [-50, +50)
    for (const r of [0, 0.001, 0.5, 0.999]) {
      const [x, y] = projectXY(
        { x: undefined, y: undefined },
        cx,
        cy,
        span,
        () => r,
      );
      expect(x).toBeGreaterThanOrEqual(cx - 50);
      expect(x).toBeLessThan(cx + 50);
      expect(y).toBeGreaterThanOrEqual(cy - 50);
      expect(y).toBeLessThan(cy + 50);
    }
  });
});

import { describe, it, expect } from "vitest";
import { colorFor, CLUSTER_COLORS } from "./clusters.js";

describe("colorFor", () => {
  it("returns the mapped hex for known types", () => {
    expect(colorFor("atom")).toBe("#F5D90A");
    expect(colorFor("gap")).toBe("#FF6B5B");
    expect(colorFor("paper")).toBe("#5DD879");
  });

  it("renders 'fact' as green (distinct from yellow atoms)", () => {
    expect(colorFor("fact")).toBe("#5DD879");
  });

  it("falls back to white for unknown types", () => {
    expect(colorFor("recipe")).toBe("#FFFFFF");
    expect(colorFor(undefined)).toBe("#FFFFFF");
    expect(colorFor(null)).toBe("#FFFFFF");
  });
});

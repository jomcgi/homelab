import { describe, it, expect } from "vitest";
import { colorFor, CLUSTER_COLORS } from "./clusters.js";

describe("colorFor", () => {
  it("returns the mapped colour for known types", () => {
    expect(colorFor("atom")).toBe("var(--cluster-atom)");
    expect(colorFor("gap")).toBe("var(--cluster-gap)");
    expect(colorFor("paper")).toBe("var(--cluster-paper)");
  });

  it("aliases legacy 'fact' type to atom colour", () => {
    expect(colorFor("fact")).toBe(CLUSTER_COLORS.atom);
  });

  it("falls back to --cluster-other for unknown types", () => {
    expect(colorFor("recipe")).toBe("var(--cluster-other)");
    expect(colorFor(undefined)).toBe("var(--cluster-other)");
    expect(colorFor(null)).toBe("var(--cluster-other)");
  });
});

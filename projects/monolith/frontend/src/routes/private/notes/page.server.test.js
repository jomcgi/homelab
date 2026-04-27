import { describe, it, expect, vi } from "vitest";
import { load } from "./+page.server.js";

describe("/notes load", () => {
  it("fetches the graph and sets the cache-control header", async () => {
    const setHeaders = vi.fn();
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [], indexed_at: null }),
    });

    const result = await load({ fetch, setHeaders });

    expect(setHeaders).toHaveBeenCalledWith(
      expect.objectContaining({
        "cache-control": expect.stringContaining("s-maxage="),
      }),
    );
    expect(result.graph).toEqual({ nodes: [], edges: [], indexed_at: null });
  });

  it("throws a 503 when the backend fetch fails", async () => {
    const setHeaders = vi.fn();
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 502 });

    await expect(load({ fetch, setHeaders })).rejects.toThrow();
  });
});

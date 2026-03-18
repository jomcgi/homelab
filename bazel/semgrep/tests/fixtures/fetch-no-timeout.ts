// Tests for fetch-no-timeout rule.

// ruleid: fetch-no-timeout
fetch("https://example.com");

// ruleid: fetch-no-timeout
fetch("https://example.com", { method: "GET" });

// ruleid: fetch-no-timeout
fetch("https://example.com", { headers: { "X-Custom": "value" } });

// ok: fetch-no-timeout
fetch("https://example.com", { signal: AbortSignal.timeout(5000) });

// ok: fetch-no-timeout
const controller = new AbortController();
fetch("https://example.com", { signal: controller.signal });

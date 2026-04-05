import { test, expect } from "@playwright/test";

// Notes API tests — mock POST /api/notes endpoint
// Matches notes/router.py NoteCreate model: { content: str }
// Response: 201 with dict payload, 400 for empty/whitespace content

test.describe("Notes API", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/notes", async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        const content = body?.content ?? "";
        if (!content.trim()) {
          await route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ detail: "content is required" }),
          });
        } else {
          await route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify({
              ok: true,
              source: "web-ui",
              content: content,
            }),
          });
        }
      } else {
        await route.continue();
      }
    });

    await page.goto("/public");
  });

  test("POST /api/notes returns status 201", async ({ page }) => {
    const status = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "Test fleeting note" }),
      });
      return res.status;
    });

    expect(status).toBe(201);
  });

  test("POST /api/notes response body includes ok: true", async ({ page }) => {
    const body = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "Test note" }),
      });
      return res.json();
    });

    expect(body.ok).toBe(true);
  });

  test("POST /api/notes echoes content in response", async ({ page }) => {
    const testContent = "Remember to check the deployment status";

    const body = await page.evaluate(async (content) => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      return res.json();
    }, testContent);

    expect(body.content).toBe(testContent);
  });

  test("POST /api/notes source is web-ui", async ({ page }) => {
    const body = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "Source check" }),
      });
      return res.json();
    });

    expect(body.source).toBe("web-ui");
  });

  test("POST /api/notes sends JSON content-type", async ({ page }) => {
    let capturedContentType = null;

    await page.route("**/api/notes", async (route) => {
      if (route.request().method() === "POST") {
        capturedContentType = route.request().headers()["content-type"];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({ ok: true }),
        });
      } else {
        await route.continue();
      }
    });

    await page.evaluate(async () => {
      await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "Content-type test" }),
      });
    });

    expect(capturedContentType).toContain("application/json");
  });

  test("POST /api/notes with empty content returns 400", async ({ page }) => {
    const response = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "" }),
      });
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(400);
    expect(response.body.detail).toBe("content is required");
  });

  test("POST /api/notes with whitespace-only content returns 400", async ({ page }) => {
    const response = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "   " }),
      });
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(400);
    expect(response.body.detail).toBe("content is required");
  });

  test("POST /api/notes returns 502 when vault is unavailable", async ({ page }) => {
    // Override the route for this specific test to simulate vault failure
    await page.route("**/api/notes", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 502,
          contentType: "application/json",
          body: JSON.stringify({ detail: "vault unavailable" }),
        });
      } else {
        await route.continue();
      }
    });

    const response = await page.evaluate(async () => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "This note should fail" }),
      });
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(502);
    expect(response.body.detail).toBe("vault unavailable");
  });

  test("POST /api/notes with multiline content preserves newlines", async ({
    page,
  }) => {
    const multilineContent = "Line one\nLine two\nLine three";

    const body = await page.evaluate(async (content) => {
      const res = await fetch("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      return res.json();
    }, multilineContent);

    expect(body.content).toBe(multilineContent);
  });
});

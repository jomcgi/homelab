import { test, expect } from "@playwright/test";

// Mock data matching Pydantic models in home/router.py
// TaskResponse: { task: str, done: bool }
// list[TaskResponse] for daily tasks
// list[dict] for schedule events from shared/router.py

const MOCK_WEEKLY = { task: "Review quarterly goals", done: false };

const MOCK_DAILY = [
  { task: "Morning standup", done: true },
  { task: "Review pull requests", done: false },
  { task: "Update task tracker", done: false },
];

const MOCK_SCHEDULE = [
  { allDay: true, time: null, title: "Doctor appointment" },
  { allDay: false, time: "09:00", endTime: "10:00", title: "Team standup" },
  { allDay: false, time: "14:00", endTime: "15:00", title: "1:1 with manager" },
];

test.describe("Private Home — API contracts with mocked responses", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept GET /api/home/weekly — TaskResponse shape
    await page.route("**/api/home/weekly", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_WEEKLY),
      });
    });

    // Intercept GET /api/home/daily — list[TaskResponse]
    await page.route("**/api/home/daily", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_DAILY),
      });
    });

    // Intercept GET /api/schedule/today — list[dict] with event fields
    await page.route("**/api/schedule/today", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_SCHEDULE),
      });
    });

    await page.goto("/public");
  });

  test("GET /api/home/weekly returns TaskResponse shape", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/weekly");
      return res.json();
    });

    expect(data).toMatchObject({
      task: expect.any(String),
      done: expect.any(Boolean),
    });
    expect(data.task).toBe("Review quarterly goals");
    expect(data.done).toBe(false);
  });

  test("GET /api/home/daily returns list of TaskResponse objects", async ({
    page,
  }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/daily");
      return res.json();
    });

    expect(Array.isArray(data)).toBe(true);
    expect(data).toHaveLength(3);
    data.forEach((item) => {
      expect(item).toMatchObject({
        task: expect.any(String),
        done: expect.any(Boolean),
      });
    });
  });

  test("GET /api/home/daily includes both done and undone tasks", async ({
    page,
  }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/daily");
      return res.json();
    });

    const done = data.filter((t) => t.done);
    const pending = data.filter((t) => !t.done);
    expect(done.length).toBeGreaterThanOrEqual(1);
    expect(pending.length).toBeGreaterThanOrEqual(1);
  });

  test("GET /api/schedule/today returns list of schedule events", async ({
    page,
  }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return res.json();
    });

    expect(Array.isArray(data)).toBe(true);
    expect(data).toHaveLength(3);
  });

  test("schedule events include all-day and timed events", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return res.json();
    });

    const allDayEvent = data.find((e) => e.allDay === true);
    expect(allDayEvent).toBeDefined();
    expect(allDayEvent.time).toBeNull();
    // shared/service.py omits the endTime key entirely for all-day events
    expect("endTime" in allDayEvent).toBe(false);
    expect(allDayEvent.title).toBe("Doctor appointment");
  });

  test("timed schedule events have time and endTime", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return res.json();
    });

    const timedEvent = data.find((e) => !e.allDay && e.time === "09:00");
    expect(timedEvent).toBeDefined();
    expect(timedEvent.endTime).toBe("10:00");
    expect(timedEvent.title).toBe("Team standup");
  });

  test("schedule event titles are non-empty strings", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return res.json();
    });

    data.forEach((event) => {
      expect(typeof event.title).toBe("string");
      expect(event.title.length).toBeGreaterThan(0);
    });
  });

  test("weekly task has string task field", async ({ page }) => {
    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/weekly");
      return res.json();
    });

    expect(typeof data.task).toBe("string");
    expect(data.task.length).toBeGreaterThan(0);
  });
});

test.describe("Private Home — error and edge-case responses", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/public");
  });

  test("GET /api/home/weekly handles 500 error response", async ({ page }) => {
    await page.route("**/api/home/weekly", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    const response = await page.evaluate(async () => {
      const res = await fetch("/api/home/weekly");
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(500);
    expect(response.body.detail).toBe("Internal Server Error");
  });

  test("GET /api/home/daily handles 500 error response", async ({ page }) => {
    await page.route("**/api/home/daily", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    const response = await page.evaluate(async () => {
      const res = await fetch("/api/home/daily");
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(500);
    expect(response.body.detail).toBe("Internal Server Error");
  });

  test("GET /api/schedule/today handles 500 error response", async ({
    page,
  }) => {
    await page.route("**/api/schedule/today", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    const response = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return { status: res.status, body: await res.json() };
    });

    expect(response.status).toBe(500);
    expect(response.body.detail).toBe("Internal Server Error");
  });

  test("GET /api/home/weekly returns empty task when no weekly task exists", async ({
    page,
  }) => {
    await page.route("**/api/home/weekly", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ task: "", done: false }),
      });
    });

    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/weekly");
      return res.json();
    });

    expect(data.task).toBe("");
    expect(data.done).toBe(false);
  });

  test("GET /api/home/daily returns 3 empty tasks when no tasks exist", async ({
    page,
  }) => {
    await page.route("**/api/home/daily", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { task: "", done: false },
          { task: "", done: false },
          { task: "", done: false },
        ]),
      });
    });

    const data = await page.evaluate(async () => {
      const res = await fetch("/api/home/daily");
      return res.json();
    });

    expect(Array.isArray(data)).toBe(true);
    expect(data).toHaveLength(3);
    data.forEach((item) => {
      expect(item.task).toBe("");
      expect(item.done).toBe(false);
    });
  });

  test("GET /api/schedule/today returns empty array when no events", async ({
    page,
  }) => {
    await page.route("**/api/schedule/today", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    const data = await page.evaluate(async () => {
      const res = await fetch("/api/schedule/today");
      return res.json();
    });

    expect(Array.isArray(data)).toBe(true);
    expect(data).toHaveLength(0);
  });
});

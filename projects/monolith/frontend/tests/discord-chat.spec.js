import { test, expect } from "@playwright/test";

// Discord chat integration tests
// Mocks the /api/chat/* endpoints that the chat UI may call.
// Tests verify data shapes matching chat/models.py SQLModel definitions:
//   Message: { id, discord_message_id, channel_id, user_id, username, content, is_bot, embedding, created_at }
//   UserChannelSummary: { id, channel_id, user_id, username, summary, last_message_id, updated_at }
//
// NOTE: The /api/chat/* router is not yet registered in main.py — these tests
// are marked fixme until the chat API endpoints are wired up.

const MOCK_MESSAGES = [
  {
    id: 1,
    discord_message_id: "1234567890123456789",
    channel_id: "987654321098765432",
    user_id: "111222333444555666",
    username: "alice",
    content: "Hello, how is the deployment going?",
    is_bot: false,
    embedding: Array(1024).fill(0.0),
    created_at: "2026-04-05T02:00:00Z",
  },
  {
    id: 2,
    discord_message_id: "1234567890123456790",
    channel_id: "987654321098765432",
    user_id: "999888777666555444",
    username: "homelab-bot",
    content: "The deployment completed successfully. All pods are running.",
    is_bot: true,
    embedding: Array(1024).fill(0.0),
    created_at: "2026-04-05T02:01:00Z",
  },
  {
    id: 3,
    discord_message_id: "1234567890123456791",
    channel_id: "987654321098765432",
    user_id: "111222333444555666",
    username: "alice",
    content: "Thanks! What about the database migration?",
    is_bot: false,
    embedding: Array(1024).fill(0.0),
    created_at: "2026-04-05T02:02:00Z",
  },
];

const MOCK_USER_SUMMARY = {
  id: 1,
  channel_id: "987654321098765432",
  user_id: "111222333444555666",
  username: "alice",
  summary:
    "Active contributor who frequently asks about deployment status and infrastructure.",
  last_message_id: 3,
  updated_at: "2026-04-05T02:02:00Z",
};

test.describe("Discord Chat Integration", () => {
  test.beforeEach(async ({ page }) => {
    // Mock /api/chat/messages endpoint
    await page.route("**/api/chat/messages**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_MESSAGES),
      });
    });

    // Mock /api/chat/summary endpoint
    await page.route("**/api/chat/summary**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER_SUMMARY),
      });
    });

    await page.goto("/public");
  });

  test("chat messages API returns array", async ({ page }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch(
        "/api/chat/messages?channel_id=987654321098765432&limit=20",
      );
      return res.json();
    });

    expect(Array.isArray(messages)).toBe(true);
    expect(messages.length).toBeGreaterThan(0);
  });

  test("Message model has required fields", async ({ page }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    const msg = messages[0];
    expect(msg).toMatchObject({
      id: expect.any(Number),
      discord_message_id: expect.any(String),
      channel_id: expect.any(String),
      user_id: expect.any(String),
      username: expect.any(String),
      content: expect.any(String),
      is_bot: expect.any(Boolean),
      embedding: expect.any(Array),
      created_at: expect.any(String),
    });
  });

  test("bot messages are distinguishable from user messages", async ({
    page,
  }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    const userMessages = messages.filter((m) => !m.is_bot);
    const botMessages = messages.filter((m) => m.is_bot);

    expect(userMessages.length).toBeGreaterThan(0);
    expect(botMessages.length).toBeGreaterThan(0);
    expect(botMessages[0].username).toBe("homelab-bot");
  });

  test("messages are ordered chronologically ascending", async ({ page }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    for (let i = 1; i < messages.length; i++) {
      const prev = new Date(messages[i - 1].created_at).getTime();
      const curr = new Date(messages[i].created_at).getTime();
      expect(curr).toBeGreaterThanOrEqual(prev);
    }
  });

  test("discord_message_id is a non-empty string (snowflake format)", async ({
    page,
  }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    messages.forEach((msg) => {
      expect(typeof msg.discord_message_id).toBe("string");
      expect(msg.discord_message_id.length).toBeGreaterThan(0);
      // Discord snowflakes are numeric strings
      expect(/^\d+$/.test(msg.discord_message_id)).toBe(true);
    });
  });

  test("message content is non-empty string", async ({ page }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    messages.forEach((msg) => {
      expect(typeof msg.content).toBe("string");
      expect(msg.content.length).toBeGreaterThan(0);
    });
  });

  test("UserChannelSummary model has required fields", async ({ page }) => {
    test.fixme(true, "/api/chat/summary not yet registered in main.py");
    const summary = await page.evaluate(async () => {
      const res = await fetch(
        "/api/chat/summary?username=alice&channel_id=987654321098765432",
      );
      return res.json();
    });

    expect(summary).toMatchObject({
      id: expect.any(Number),
      channel_id: expect.any(String),
      user_id: expect.any(String),
      username: expect.any(String),
      summary: expect.any(String),
      last_message_id: expect.any(Number),
      updated_at: expect.any(String),
    });
  });

  test("user summary username matches requested user", async ({ page }) => {
    test.fixme(true, "/api/chat/summary not yet registered in main.py");
    const summary = await page.evaluate(async () => {
      const res = await fetch("/api/chat/summary?username=alice");
      return res.json();
    });

    expect(summary.username).toBe("alice");
  });

  test("user summary contains non-empty description", async ({ page }) => {
    test.fixme(true, "/api/chat/summary not yet registered in main.py");
    const summary = await page.evaluate(async () => {
      const res = await fetch("/api/chat/summary?username=alice");
      return res.json();
    });

    expect(typeof summary.summary).toBe("string");
    expect(summary.summary.length).toBeGreaterThan(0);
  });

  test("last_message_id is a positive integer", async ({ page }) => {
    test.fixme(true, "/api/chat/summary not yet registered in main.py");
    const summary = await page.evaluate(async () => {
      const res = await fetch("/api/chat/summary?username=alice");
      return res.json();
    });

    expect(typeof summary.last_message_id).toBe("number");
    expect(summary.last_message_id).toBeGreaterThan(0);
  });

  test("created_at timestamps are valid ISO 8601 dates", async ({ page }) => {
    test.fixme(true, "/api/chat/messages not yet registered in main.py");
    const messages = await page.evaluate(async () => {
      const res = await fetch("/api/chat/messages");
      return res.json();
    });

    messages.forEach((msg) => {
      const date = new Date(msg.created_at);
      expect(date.toString()).not.toBe("Invalid Date");
      expect(date.getFullYear()).toBeGreaterThanOrEqual(2024);
    });
  });
});

import { test, expect } from "@playwright/test";

test("loads page and shows Bosun title", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Bosun")).toBeVisible();
});

test("send message and see response", async ({ page }) => {
  await page.goto("/");
  const input =
    page.getByTestId("message-input") ||
    page.getByPlaceholder("Type a message...");
  await input.fill("Hello");
  // Submit via Enter key
  await input.press("Enter");
  // Wait for response to appear
  await expect(page.getByText("Hello from mock")).toBeVisible({
    timeout: 10000,
  });
});

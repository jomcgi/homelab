import { test, expect } from "@playwright/test";

test.describe("Public Route (/public)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/public");
    await page.waitForLoadState("load");
  });

  test("renders heading with correct text", async ({ page }) => {
    const heading = page.locator("h1");
    await expect(heading).toBeVisible();
    await expect(heading).toHaveText("public.jomcgi.dev");
  });

  test("page URL matches /public route", async ({ page }) => {
    await expect(page).toHaveURL(/\/public/);
  });

  test("returns HTTP 200", async ({ page }) => {
    const response = await page.goto("/public");
    expect(response?.status()).toBe(200);
  });

  test("page has no visible error state", async ({ page }) => {
    // SvelteKit error pages typically include 'Error' or status codes
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toMatch(/404|500|error/i);
  });

  test("heading is the only h1 on the page", async ({ page }) => {
    const headings = page.locator("h1");
    await expect(headings).toHaveCount(1);
  });

  test("global layout renders around page content", async ({ page }) => {
    // The root layout injects global CSS — confirm body exists and children render
    await expect(page.locator("body")).toBeVisible();
    await expect(page.locator("h1")).toContainText("public.jomcgi.dev");
  });
});

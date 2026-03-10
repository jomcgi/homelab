import { test, expect } from "@playwright/test";

test.describe("Deployment Health Checks", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the fetch request for bundle data
    await page.route("**/bundle.brotli", async (route) => {
      const mockBundle = {
        v: 2,
        g: Math.floor(Date.now() / 1000),
        d: [],
      };

      const mockData = JSON.stringify(mockBundle);
      const buffer = new TextEncoder().encode(mockData);

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: buffer,
      });
    });

    // Mock BrotliDecompress function
    await page.addInitScript(() => {
      window.BrotliDecompress = async (buffer) => {
        const decoder = new TextDecoder();
        return decoder.decode(buffer);
      };
    });
  });

  test("should load main page without errors", async ({ page }) => {
    // Monitor console errors
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        errors.push(msg.text());
      }
    });

    await page.goto("/");

    // Check that page loads successfully
    await expect(page).toHaveTitle("Hike Finder");

    // Verify no critical console errors
    const criticalErrors = errors.filter(
      (error) =>
        !error.includes("favicon") && // Ignore favicon errors
        !error.includes("woff2") && // Ignore font loading issues
        !error.includes("_gaq") && // Ignore analytics issues
        !error.includes("gtag"), // Ignore Google Analytics issues
    );

    if (criticalErrors.length > 0) {
      console.log("Console errors detected:", criticalErrors);
      expect(criticalErrors).toHaveLength(0);
    }
  });

  test("should load all critical assets", async ({ page }) => {
    await page.goto("/");

    // Check that JavaScript loads
    await expect(page.locator("#search-btn")).toBeVisible();

    // Check that CSS loads (verify styled elements)
    const header = page.locator("header");
    await expect(header).toBeVisible();

    // Verify form elements are present
    await expect(page.locator("#latitude")).toBeVisible();
    await expect(page.locator("#longitude")).toBeVisible();
    await expect(page.locator("#radius")).toBeVisible();
  });

  test("should have working search functionality", async ({ page }) => {
    await page.goto("/");

    // Fill in basic form data
    await page.locator("#latitude").fill("55.8642");
    await page.locator("#longitude").fill("-4.2518");
    await page.locator("#radius").fill("25");

    // Click search button
    await page.locator("#search-btn").click();

    // Wait for search to complete (increased timeout for health check)
    await page.waitForTimeout(3000);

    // Check that search doesn't crash the page (title should still be correct)
    await expect(page).toHaveTitle("Hike Finder");

    // Check that the form is still functional after search
    await expect(page.locator("#search-btn")).toBeEnabled();
  });
});

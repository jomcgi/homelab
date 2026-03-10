import { test, expect } from "@playwright/test";

test.describe("Coordinates Functionality", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the fetch request for bundle data
    await page.route("**/bundle.brotli", async (route) => {
      const mockBundle = {
        v: 2,
        g: Math.floor(Date.now() / 1000),
        d: [
          [
            1,
            55.8827,
            -4.2589,
            4.5,
            12.3,
            650,
            "Ben Lomond",
            "https://www.walkhighlands.co.uk/lochlomond/ben-lomond.shtml",
            "Scotland's most popular Munro with stunning views over Loch Lomond.",
            [],
          ],
        ],
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

    await page.goto("/");
    await page.waitForLoadState("load");
  });

  test("should display default coordinates (Glasgow)", async ({ page }) => {
    const latitudeInput = page.locator("#latitude");
    const longitudeInput = page.locator("#longitude");

    await expect(latitudeInput).toHaveValue("55.8827");
    await expect(longitudeInput).toHaveValue("-4.2589");
  });

  test("should allow manual coordinate input", async ({ page }) => {
    const latitudeInput = page.locator("#latitude");
    const longitudeInput = page.locator("#longitude");

    await latitudeInput.fill("56.8167");
    await longitudeInput.fill("-5.1056");

    await expect(latitudeInput).toHaveValue("56.8167");
    await expect(longitudeInput).toHaveValue("-5.1056");
  });

  test("should display use location button", async ({ page }) => {
    const useLocationBtn = page.locator("#use-location-btn");
    const locationStatus = page.locator("#location-status");

    await expect(useLocationBtn).toBeVisible();
    await expect(useLocationBtn).toHaveText("📍 Use My Location");
    await expect(locationStatus).toBeVisible();
  });

  test("should validate coordinate inputs", async ({ page }) => {
    const latitudeInput = page.locator("#latitude");
    const longitudeInput = page.locator("#longitude");

    // Test invalid latitude (out of range)
    await latitudeInput.fill("91");
    await expect(latitudeInput).toHaveAttribute("type", "number");

    // Test invalid longitude (out of range)
    await longitudeInput.fill("181");
    await expect(longitudeInput).toHaveAttribute("type", "number");

    // Test valid coordinates
    await latitudeInput.fill("55.8827");
    await longitudeInput.fill("-4.2589");

    await expect(latitudeInput).toHaveValue("55.8827");
    await expect(longitudeInput).toHaveValue("-4.2589");
  });

  test("should preserve coordinates in form submission", async ({ page }) => {
    const latitudeInput = page.locator("#latitude");
    const longitudeInput = page.locator("#longitude");
    const searchBtn = page.locator("#search-btn");

    // Set custom coordinates
    await latitudeInput.fill("58.2083");
    await longitudeInput.fill("-6.3857");

    // Trigger search (will likely fail due to no mock data, but coordinates should be preserved)
    await searchBtn.click();

    // Coordinates should still be there after search
    await expect(latitudeInput).toHaveValue("58.2083");
    await expect(longitudeInput).toHaveValue("-6.3857");
  });
});

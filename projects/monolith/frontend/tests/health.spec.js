import { test, expect } from "@playwright/test";

test.describe("Application Health", () => {
  test("page loads without console errors", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto("/public");
    await page.waitForLoadState("networkidle");

    expect(consoleErrors).toHaveLength(0);
  });

  test("layout CSS variables are defined on :root", async ({ page }) => {
    await page.goto("/public");

    const cssVars = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      return {
        font: style.getPropertyValue("--font").trim(),
        fg: style.getPropertyValue("--fg").trim(),
        bg: style.getPropertyValue("--bg").trim(),
        border: style.getPropertyValue("--border").trim(),
        surface: style.getPropertyValue("--surface").trim(),
        danger: style.getPropertyValue("--danger").trim(),
      };
    });

    expect(cssVars.font).toContain("Space Mono");
    expect(cssVars.fg).toBeTruthy();
    expect(cssVars.bg).toBeTruthy();
    expect(cssVars.border).toBeTruthy();
    expect(cssVars.surface).toBeTruthy();
    expect(cssVars.danger).toBeTruthy();
  });

  test("global reset styles apply — box-sizing border-box", async ({ page }) => {
    await page.goto("/public");

    const boxSizing = await page.evaluate(() => {
      return getComputedStyle(document.body).boxSizing;
    });

    expect(boxSizing).toBe("border-box");
  });

  test("body has overflow hidden from global styles", async ({ page }) => {
    await page.goto("/public");

    const overflow = await page.evaluate(() => {
      return getComputedStyle(document.body).overflow;
    });

    expect(overflow).toBe("hidden");
  });

  test("Space Mono font family CSS variable is set", async ({ page }) => {
    await page.goto("/public");

    const fontVar = await page.evaluate(() => {
      return getComputedStyle(document.documentElement)
        .getPropertyValue("--font")
        .trim();
    });

    expect(fontVar).toContain("Space Mono");
  });

  test("design system fg-secondary and fg-tertiary variables are set", async ({
    page,
  }) => {
    await page.goto("/public");

    const vars = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      return {
        fgSecondary: style.getPropertyValue("--fg-secondary").trim(),
        fgTertiary: style.getPropertyValue("--fg-tertiary").trim(),
      };
    });

    expect(vars.fgSecondary).toBeTruthy();
    expect(vars.fgTertiary).toBeTruthy();
  });
});

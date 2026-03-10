import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 6 : 4,
  reporter: "list",
  use: {
    trace: "on-first-retry",
    baseURL: process.env.CI
      ? "http://localhost:33999"
      : "http://localhost:33999",
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: ["--no-sandbox", "--disable-setuid-sandbox"],
        },
      },
    },
  ],

  webServer: {
    command: process.env.CI
      ? "python3 -m http.server 33999 --directory public"
      : "python3 -m http.server 33999 --directory public",
    reuseExistingServer: false,
  },
});

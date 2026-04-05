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
    baseURL: "http://localhost:4173",
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
    command: "npm run build && PORT=4173 node build/index.js",
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
});

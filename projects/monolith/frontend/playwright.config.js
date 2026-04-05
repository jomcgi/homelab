import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.PORT ?? "4173";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 6 : 4,
  reporter: "list",
  use: {
    trace: "on-first-retry",
    baseURL: `http://localhost:${PORT}`,
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
    command: `PORT=${PORT} node build/index.js`,
    port: parseInt(PORT, 10),
    reuseExistingServer: !process.env.CI,
  },
});

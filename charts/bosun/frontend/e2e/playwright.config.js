import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  use: {
    baseURL: "http://localhost:8420",
  },
  webServer: {
    command: "python3 e2e/mock-server.py",
    port: 8420,
    reuseExistingServer: !process.env.CI,
  },
});

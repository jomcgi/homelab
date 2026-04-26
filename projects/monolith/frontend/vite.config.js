import path from "node:path";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    target: "es2022",
  },
  server: {
    fs: {
      allow: [path.resolve("../home/frontend")],
    },
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

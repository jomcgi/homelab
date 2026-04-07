import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    target: "es2022",
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

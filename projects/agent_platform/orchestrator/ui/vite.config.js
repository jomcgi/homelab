import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/agents": "http://localhost:8080",
      "/infer": "http://localhost:8080",
      "/jobs": "http://localhost:8080",
      "/pipeline": "http://localhost:8080",
      "/health": "http://localhost:8080",
      "/stats": "http://localhost:8080",
    },
  },
});

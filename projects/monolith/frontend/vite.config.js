import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    target: "es2022",
  },
  ssr: {
    // The runtime image ships only the SvelteKit `build/` output — there is
    // no node_modules. Any package imported by SSR-rendered code must be
    // bundled into the server chunks, not externalized.
    noExternal: ["@dagrejs/dagre"],
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

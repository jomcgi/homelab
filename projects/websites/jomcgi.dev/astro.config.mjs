// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import tailwind from "@astrojs/tailwind";

// https://astro.build/config
export default defineConfig({
  integrations: [
    react(),
    tailwind(),
    {
      name: "force-es2022",
      hooks: {
        "astro:build:setup": ({ vite }) => {
          vite.build = { ...vite.build, target: "es2022" };
        },
      },
    },
  ],
  vite: {
    build: {
      target: "es2022",
    },
    server: {
      host: true,
      hmr: {
        clientPort: 443,
        protocol: "wss",
      },
    },
  },
  server: {
    host: true,
    allowedHosts: ["claude.jomcgi.dev"],
  },
});

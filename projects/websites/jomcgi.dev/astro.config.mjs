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
      name: "esnext-target",
      hooks: {
        "astro:build:setup": ({ updateConfig }) => {
          updateConfig({
            build: { target: "esnext" },
            esbuild: { target: "esnext" },
          });
        },
      },
    },
  ],
  vite: {
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

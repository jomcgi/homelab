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
          // Force es2022 at top level
          vite.build = vite.build || {};
          vite.build.target = "es2022";
          // Force es2022 in Vite 6 environment API (client build)
          if (vite.environments?.client?.build) {
            vite.environments.client.build.target = "es2022";
          }
        },
      },
    },
  ],
  vite: {
    build: {
      target: "es2022",
    },
    environments: {
      client: {
        build: {
          target: "es2022",
        },
      },
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

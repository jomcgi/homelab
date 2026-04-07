import { defineConfig } from "vitepress";
import adrSidebar from "./adr-sidebar.json";

export default defineConfig({
  vite: {
    build: {
      target: "esnext",
    },
    esbuild: {
      target: "esnext",
    },
  },
  title: "Homelab Docs",
  description: "Documentation for jomcgi/homelab",

  rewrites: {
    "docs_rewrite/:rest*": ":rest*",
  },

  themeConfig: {
    nav: [
      { text: "Architecture", link: "/docs/services" },
      { text: "ADRs", link: "/docs/decisions/" },
      { text: "GitHub", link: "https://github.com/jomcgi/homelab" },
    ],

    sidebar: [
      {
        text: "Architecture",
        items: [
          { text: "Services", link: "/docs/services" },
          { text: "Security", link: "/docs/security" },
          { text: "Observability", link: "/docs/observability" },
          { text: "Alerting", link: "/docs/observability-alerting" },
          { text: "Contributing", link: "/docs/contributing" },
          { text: "Agent Platform", link: "/docs/agents" },
        ],
      },
      {
        text: "ADRs",
        collapsed: false,
        items: [{ text: "Overview", link: "/docs/decisions/" }, ...adrSidebar],
      },
    ],

    search: {
      provider: "local",
    },

    socialLinks: [
      { icon: "github", link: "https://github.com/jomcgi/homelab" },
    ],
  },
});

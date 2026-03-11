import { defineConfig } from "vitepress";

export default defineConfig({
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
        items: [
          { text: "Overview", link: "/docs/decisions/" },
          {
            text: "Agents",
            collapsed: true,
            items: [
              {
                text: "001 - Background Agents",
                link: "/docs/decisions/agents/001-background-agents",
              },
              {
                text: "002 - OpenHands Sandbox",
                link: "/docs/decisions/agents/002-openhands-agent-sandbox",
              },
              {
                text: "003 - Context Forge",
                link: "/docs/decisions/agents/003-context-forge",
              },
              {
                text: "004 - Autonomous Agents",
                link: "/docs/decisions/agents/004-autonomous-agents",
              },
              {
                text: "005 - Role-Based MCP Access",
                link: "/docs/decisions/agents/005-role-based-mcp-access",
              },
              {
                text: "006 - OIDC Auth MCP Gateway",
                link: "/docs/decisions/agents/006-oidc-auth-mcp-gateway",
              },
              {
                text: "007 - Agent Run Orchestration",
                link: "/docs/decisions/agents/007-agent-orchestrator",
              },
              {
                text: "008 - Cluster Patrol Loop Resilience",
                link: "/docs/decisions/agents/008-cluster-patrol-loop-resilience",
              },
            ],
          },
          {
            text: "Docs",
            collapsed: true,
            items: [
              {
                text: "001 - Static Docs Site",
                link: "/docs/decisions/docs/001-static-docs-site",
              },
            ],
          },
          {
            text: "Networking",
            collapsed: true,
            items: [
              {
                text: "001 - Cloudflare Envoy Gateway",
                link: "/docs/decisions/networking/001-cloudflare-envoy-gateway",
              },
            ],
          },
          {
            text: "Security",
            collapsed: true,
            items: [
              {
                text: "001 - Bazel Semgrep",
                link: "/docs/decisions/security/001-bazel-semgrep",
              },
            ],
          },
        ],
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

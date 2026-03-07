import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Homelab Docs',
  description: 'Documentation for jomcgi/homelab',

  rewrites: {
    'docs_rewrite/:rest*': ':rest*',
  },

  themeConfig: {
    nav: [
      { text: 'Architecture', link: '/architecture/services' },
      { text: 'GitHub', link: 'https://github.com/jomcgi/homelab' },
    ],

    sidebar: [
      {
        text: 'Architecture',
        items: [
          { text: 'Services', link: '/architecture/services' },
          { text: 'Security', link: '/architecture/security' },
          { text: 'Observability', link: '/architecture/observability' },
          { text: 'Alerting', link: '/architecture/observability-alerting' },
          { text: 'Contributing', link: '/architecture/contributing' },
        ],
      },
      {
        text: 'ADRs',
        collapsed: false,
        items: [
          {
            text: 'Agents',
            collapsed: true,
            items: [
              { text: '001 - Background Agents', link: '/architecture/decisions/agents/001-background-agents' },
              { text: '002 - OpenHands Sandbox', link: '/architecture/decisions/agents/002-openhands-agent-sandbox' },
              { text: '003 - Context Forge', link: '/architecture/decisions/agents/003-context-forge' },
              { text: '004 - Autonomous Agents', link: '/architecture/decisions/agents/004-autonomous-agents' },
              { text: '005 - Role-Based MCP Access', link: '/architecture/decisions/agents/005-role-based-mcp-access' },
              { text: '006 - OIDC Auth MCP Gateway', link: '/architecture/decisions/agents/006-oidc-auth-mcp-gateway' },
            ],
          },
          {
            text: 'Docs',
            collapsed: true,
            items: [
              { text: '001 - Static Docs Site', link: '/architecture/decisions/docs/001-static-docs-site' },
            ],
          },
          {
            text: 'Networking',
            collapsed: true,
            items: [
              { text: '001 - Cloudflare Envoy Gateway', link: '/architecture/decisions/networking/001-cloudflare-envoy-gateway' },
            ],
          },
          {
            text: 'Security',
            collapsed: true,
            items: [
              { text: '001 - Bazel Semgrep', link: '/architecture/decisions/security/001-bazel-semgrep' },
            ],
          },
        ],
      },
    ],

    search: {
      provider: 'local',
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/jomcgi/homelab' },
    ],
  },
})

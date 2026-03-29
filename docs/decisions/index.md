# Architecture Decision Records

ADRs document significant architectural decisions and their context.

## Agents

| ADR                                                                       | Decision                                                      |
| ------------------------------------------------------------------------- | ------------------------------------------------------------- |
| [001 - Background Agents](agents/001-background-agents.md)                | Kubernetes-native agent execution with sandbox isolation      |
| [002 - OpenHands Agent Sandbox](agents/002-openhands-agent-sandbox.md)    | OpenHands as the agent runtime framework                      |
| [003 - Context Forge](agents/003-context-forge.md)                        | IBM Context Forge as the MCP gateway                          |
| [004 - Autonomous Agents](agents/004-autonomous-agents.md)                | Design for fully autonomous agent workflows                   |
| [005 - Role-Based MCP Access](agents/005-role-based-mcp-access.md)        | Role-based access control for MCP tool servers                |
| [006 - OIDC Auth MCP Gateway](agents/006-oidc-auth-mcp-gateway.md)        | OAuth 2.1 / OIDC authentication for remote MCP access         |
| [007 - Agent Run Orchestration Service](agents/007-agent-orchestrator.md) | Dedicated service for dispatching and tracking agent job runs |

## Docs

| ADR                                                    | Decision                                 |
| ------------------------------------------------------ | ---------------------------------------- |
| [001 - Static Docs Site](docs/001-static-docs-site.md) | VitePress for architecture documentation |

## Networking

| ADR                                                                          | Decision                                      |
| ---------------------------------------------------------------------------- | --------------------------------------------- |
| [001 - Cloudflare Envoy Gateway](networking/001-cloudflare-envoy-gateway.md) | Cloudflare Tunnel + Envoy Gateway for ingress |

## Security

| ADR                                                                                | Decision                                                        |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| [001 - Bazel Semgrep](security/001-bazel-semgrep.md)                               | Semgrep SAST integrated via Bazel rules                         |
| [002 - Semgrep Rule Generation via RL](security/002-semgrep-rule-generation-rl.md) | RL-finetuned Qwen 3.5 9B for generating Semgrep rules from CVEs |

## Tooling

| ADR                                                                           | Decision                                                                      |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| [001 - OCI Tool Distribution](tooling/001-oci-tool-distribution.md)           | Multi-arch OCI image for developer tools, eliminating local Bazel             |
| [002 - Service Deployment Tooling](tooling/002-service-deployment-tooling.md) | Copier template to scaffold new services, eliminating per-service boilerplate |

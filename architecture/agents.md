# Agent Platform

This document describes the agent infrastructure running in the cluster.

## Overview

The agent platform enables autonomous AI agents to execute tasks with access to cluster tooling. It spans three environments: a cluster-critical controller, production agent runtimes and tool servers, and development sandboxes.

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Agent Sandbox Controller                         │
│                     (cluster-critical)                               │
├─────────────────────────────────────────────────────────────────────┤
│  Manages lifecycle of isolated agent pods across namespaces         │
│  Charts: charts/agent-sandbox                                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ creates pods
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Runtimes                                │
├──────────────────────────────┬──────────────────────────────────────┤
│  Goose Sandboxes (prod)      │  Grimoire (dev)                      │
│  Autonomous coding agents    │  D&D knowledge management            │
│  charts/goose-sandboxes      │  charts/grimoire                     │
└──────────────────────────────┴──────────────────────────────────────┘
                                 │
                                 │ LLM requests
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           LiteLLM                                    │
│                           (prod)                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Unified LLM API proxy — routes requests to:                        │
│  - llama-cpp (local GPU inference)                                  │
│  - External providers (Anthropic, OpenAI)                           │
│  Charts: charts/litellm                                             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ tool calls
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MCP Tool Infrastructure                           │
│                    (prod, mcp-gateway namespace)                     │
├──────────────────────────────┬──────────────────────────────────────┤
│  Context Forge               │  MCP Servers                         │
│  IBM MCP gateway that        │  Individual tool servers:            │
│  aggregates and routes       │  - ArgoCD MCP                       │
│  tool calls to backends      │  - Kubernetes MCP                   │
│                              │  - BuildBuddy MCP                   │
│  charts/context-forge        │  - SigNoz MCP                       │
│                              │  charts/mcp-servers                  │
├──────────────────────────────┴──────────────────────────────────────┤
│  MCP OAuth Proxy                                                    │
│  OAuth 2.1 auth layer for remote MCP access (e.g., Claude Desktop) │
│  charts/mcp-oauth-proxy                                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow

1. An agent (Goose, Claude Code) needs to perform a cluster operation
2. The agent calls a tool via MCP protocol
3. **Context Forge** receives the call and routes it to the appropriate MCP server
4. The **MCP server** (e.g., Kubernetes MCP) executes the operation against the cluster API
5. Results flow back through Context Forge to the agent

For remote access (e.g., Claude Desktop connecting from outside the cluster):
- Requests first pass through **MCP OAuth Proxy** for authentication
- The proxy validates the OAuth 2.1 token and forwards to Context Forge

## Related ADRs

- [001 - Background Agents](decisions/agents/001-background-agents.md)
- [002 - OpenHands Agent Sandbox](decisions/agents/002-openhands-agent-sandbox.md)
- [003 - Context Forge](decisions/agents/003-context-forge.md)
- [004 - Autonomous Agents](decisions/agents/004-autonomous-agents.md)
- [005 - Role-Based MCP Access](decisions/agents/005-role-based-mcp-access.md)
- [006 - OIDC Auth MCP Gateway](decisions/agents/006-oidc-auth-mcp-gateway.md)

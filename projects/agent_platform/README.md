# Agent Platform

Autonomous AI agents in isolated Kubernetes sandbox pods.

## Overview

Claude and Goose agents dispatched by a Go orchestrator over NATS JetStream, with tool access governed by Context Forge (IBM's MCP gateway) and RBAC-scoped per team. External access authenticated via Cloudflare Managed OAuth.

See [docs/agents.md](../../docs/agents.md) for the full architecture.

| Component                | Description                                              |
| ------------------------ | -------------------------------------------------------- |
| **orchestrator**         | Go service that dispatches agent jobs via NATS JetStream |
| **sandboxes**            | Isolated Kubernetes pod definitions for agent execution  |
| **cluster_agents**       | Agent configurations for cluster-scoped operations       |
| **api_gateway**          | Context Forge MCP gateway with RBAC-scoped tool access   |
| **goose_agent**          | Goose agent container and configuration                  |
| **llama_cpp**            | On-cluster LLM inference (Gemma 4)                       |
| **llama_cpp_embeddings** | On-cluster embedding inference (voyage-4-nano)           |
| **vllm**                 | Alternative LLM serving backend                          |

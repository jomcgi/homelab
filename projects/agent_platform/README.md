# Agent Platform

Autonomous AI agents in isolated Kubernetes sandbox pods.

## Overview

Claude and Goose agents dispatched by a Go orchestrator over NATS JetStream, with tool access governed by Context Forge (IBM's MCP gateway) and RBAC-scoped per team. External access authenticated via Cloudflare Managed OAuth.

See [docs/agents.md](../../docs/agents.md) for the full architecture.

| Component                | Description |
| ------------------------ | ----------- |
| **orchestrator**         | Go service that dispatches agent jobs via NATS JetStream |
| **sandboxes**            | Shell setup scripts for MCP profiles; Kubernetes sandbox pod definitions live in `chart/sandboxes/` and `chart/agent-sandbox/` |
| **cluster_agents**       | Go service that monitors cluster health and runs autonomous improvement agents (patrol, escalator, PR fix, README freshness, test coverage, etc.) |
| **api_gateway**          | Nginx-based API gateway with route-based backend selection for api.jomcgi.dev |
| **goose_agent**          | Goose agent container and configuration |
| **llama_cpp**            | On-cluster LLM inference (model configured per environment) |
| **llama_cpp_embeddings** | On-cluster embedding inference (model configured per environment) |
| **vllm**                 | Alternative LLM serving backend (Helm chart and values only — not wired to ArgoCD) |
| **chart**                | Umbrella Helm chart for all agent platform components |
| **deploy**               | ArgoCD Application, kustomization, and cluster-specific values |

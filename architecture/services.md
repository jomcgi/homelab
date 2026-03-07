# Services Overview

This document provides an overview of all services running in the cluster.

## Core Infrastructure (cluster-critical)

| Service                      | Purpose                                                    | Chart                                                                  |
| ---------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Agent Sandbox**            | Controller for isolated agent execution pods               | [charts/agent-sandbox](../charts/agent-sandbox/)                       |
| **ArgoCD**                   | GitOps controller for declarative cluster management       | [charts/argocd](../charts/argocd/)                                     |
| **ArgoCD Image Updater**     | Automatic image updates for ArgoCD-managed applications    | [charts/argocd-image-updater](../charts/argocd-image-updater/)         |
| **cert-manager**             | X.509 certificate management; required by Linkerd for mTLS | [charts/cert-manager](../charts/cert-manager/)                         |
| **CoreDNS**                  | Cluster DNS resolution for Kubernetes services             | [charts/coredns](../charts/coredns/)                                   |
| **Kyverno**                  | Policy engine with auto OTEL/Linkerd injection             | [charts/kyverno](../charts/kyverno/)                                   |
| **Linkerd**                  | Service mesh providing default mTLS and metrics; optional tracing when enabled | [charts/linkerd](../charts/linkerd/)                                   |
| **Longhorn**                 | Distributed persistent storage with automated backups      | [charts/longhorn](../charts/longhorn/)                                 |
| **NVIDIA GPU Operator**      | GPU support for LLM inference workloads                    | [charts/nvidia-gpu-operator](../charts/nvidia-gpu-operator/)           |
| **OpenTelemetry Operator**   | Auto-instrumentation for Go, Python, Node.js               | [charts/opentelemetry-operator](../charts/opentelemetry-operator/)     |
| **SigNoz**                   | Self-hosted observability (metrics, logs, traces)          | [charts/signoz](../charts/signoz/)                                     |
| **SigNoz Dashboard Sidecar** | GitOps sidecar for syncing SigNoz dashboards               | [charts/signoz-dashboard-sidecar](../charts/signoz-dashboard-sidecar/) |
| **1Password Operator**       | Secret management via OnePasswordItem CRDs                 | External chart (Helm install, outside ArgoCD)                          |

## Production Services (prod)

| Service               | Purpose                                     | Chart                                                    |
| --------------------- | ------------------------------------------- | -------------------------------------------------------- |
| **API Gateway**       | External service routing with rate limiting | [charts/api-gateway](../charts/api-gateway/)             |
| **Cloudflare Tunnel** | Zero Trust ingress (no open firewall ports) | [charts/cloudflare-tunnel](../charts/cloudflare-tunnel/) |
| **Context Forge**     | MCP gateway for aggregating tool servers    | [charts/context-forge](../charts/context-forge/)         |
| **gh-arc-controller** | GitHub Actions Runner Controller            | [charts/gh-arc-controller](../charts/gh-arc-controller/) |
| **gh-arc-runners**    | Self-hosted runners with Docker-in-Docker   | [charts/gh-arc-runners](../charts/gh-arc-runners/)       |
| **Goose Sandboxes**   | Goose agent sandbox deployments             | [charts/goose-sandboxes](../charts/goose-sandboxes/)     |
| **Knowledge Graph**   | RSS scraping, embedding, and MCP search     | [charts/knowledge-graph](../charts/knowledge-graph/)     |
| **LiteLLM**           | LLM API proxy for agents                    | [charts/litellm](../charts/litellm/)                     |
| **llama-cpp**         | Local LLM inference (Hermes 4.3-36B)        | [charts/llama-cpp](../charts/llama-cpp/)                 |
| **MCP OAuth Proxy**   | OAuth 2.1 auth layer for remote MCP access  | [charts/mcp-oauth-proxy](../charts/mcp-oauth-proxy/)     |
| **MCP Servers**       | Consolidated ArgoCD, K8s, BB, SigNoz MCP    | [charts/mcp-servers](../charts/mcp-servers/)             |
| **NATS**              | High-performance messaging with JetStream   | [charts/nats](../charts/nats/)                           |
| **SeaweedFS**         | Distributed S3-compatible object storage    | [charts/seaweedfs](../charts/seaweedfs/)                 |
| **Todo**              | Git-backed todo list with static UI         | [charts/todo](../charts/todo/)                           |
| **Trips**             | Trip management service                     | [charts/trips](../charts/trips/)                         |

## Development Services (dev)

| Service             | Purpose                                          | Chart                                                      |
| ------------------- | ------------------------------------------------ | ---------------------------------------------------------- |
| **Grimoire**        | D&D knowledge management with Redis              | [charts/grimoire](../charts/grimoire/)                     |
| **Marine**          | Real-time AIS vessel tracking (ships.jomcgi.dev) | [charts/marine](../charts/marine/)                         |
| **OCI Model Cache** | HuggingFace model caching operator               | [operators/oci-model-cache](../operators/oci-model-cache/) |
| **Stargazer**       | Dark sky location finder with weather scoring    | [charts/stargazer](../charts/stargazer/)                   |

## Static Websites

| Site                 | Description                                                  |
| -------------------- | ------------------------------------------------------------ |
| **docs.jomcgi.dev**  | Architecture docs and ADRs (VitePress, Cloudflare Pages)     |
| **hikes.jomcgi.dev** | Hiking route finder (static, Cloudflare R2)                  |
| **jomcgi.dev**       | Personal website (Astro, Cloudflare Pages)                   |
| **ships.jomcgi.dev** | Real-time vessel tracking UI (React/MapLibre)                |
| **trips.jomcgi.dev** | Road trip tracker and photo viewer (Astro, Cloudflare Pages) |

## Service Details

For detailed information about specific services, see the README in each chart:

- `charts/<service>/README.md`

# Services Overview

This document provides an overview of all services running in the cluster.

## Core Infrastructure (cluster-critical)

| Service                  | Purpose                                                 | Chart                                                          |
| ------------------------ | ------------------------------------------------------- | -------------------------------------------------------------- |
| **ArgoCD**               | GitOps controller for declarative cluster management    | [charts/argocd](../charts/argocd/)                             |
| **ArgoCD Image Updater** | Automatic image updates for ArgoCD-managed applications | [charts/argocd-image-updater](../charts/argocd-image-updater/) |
| **cert-manager**         | X.509 certificate management (required by Linkerd)      | [charts/cert-manager](../charts/cert-manager/)                 |
| **CoreDNS**              | Cluster DNS resolution for Kubernetes services          | [charts/coredns](../charts/coredns/)                           |
| **Linkerd**              | Service mesh for automatic distributed tracing and mTLS | [charts/linkerd](../charts/linkerd/)                           |
| **Kyverno**              | Policy engine with auto OTEL/Linkerd injection          | [charts/kyverno](../charts/kyverno/)                           |
| **Longhorn**             | Distributed persistent storage with automated backups   | [charts/longhorn](../charts/longhorn/)                         |
| **NVIDIA GPU Operator**  | GPU support for LLM inference workloads                 | [charts/nvidia-gpu-operator](../charts/nvidia-gpu-operator/)   |
| **SigNoz**               | Self-hosted observability (metrics, logs, traces)       | [charts/signoz](../charts/signoz/)                             |
| **SigNoz Dashboard Sidecar** | GitOps sidecar for syncing SigNoz dashboards        | [charts/signoz-dashboard-sidecar](../charts/signoz-dashboard-sidecar/) |
| **1Password Operator**   | Secret management via OnePasswordItem CRDs              | External chart                                                 |

## Production Services (prod)

| Service               | Purpose                                     | Chart                                                    |
| --------------------- | ------------------------------------------- | -------------------------------------------------------- |
| **API Gateway**       | External service routing with rate limiting | [charts/api-gateway](../charts/api-gateway/)             |
| **Cloudflare Tunnel** | Zero Trust ingress (no open firewall ports) | [charts/cloudflare-tunnel](../charts/cloudflare-tunnel/) |
| **gh-arc-controller** | GitHub Actions Runner Controller            | [charts/gh-arc-controller](../charts/gh-arc-controller/) |
| **gh-arc-runners**    | Self-hosted runners with Docker-in-Docker   | [charts/gh-arc-runners](../charts/gh-arc-runners/)       |
| **Knowledge Graph**   | RSS scraping, embedding, and MCP search     | [charts/knowledge-graph](../charts/knowledge-graph/)     |
| **llama-cpp**         | Local LLM inference (Hermes 4.3-36B)        | [charts/llama-cpp](../charts/llama-cpp/)                 |
| **NATS**              | High-performance messaging with JetStream   | [charts/nats](../charts/nats/)                           |
| **OpenClaw (Personal)** | AI assistant with Claude API (WhatsApp)   | [charts/openclaw](../charts/openclaw/)                   |
| **OpenClaw (Friends)** | AI chat bot with Hermes via llama-cpp (Discord) | [charts/openclaw](../charts/openclaw/)              |
| **Perplexica**        | Self-hosted AI search with SearXNG          | [charts/perplexica](../charts/perplexica/)               |
| **SeaweedFS**         | Distributed S3-compatible object storage    | [charts/seaweedfs](../charts/seaweedfs/)                 |
| **Todo**              | Git-backed todo list with static UI         | [charts/todo](../charts/todo/)                           |
| **Trips**             | Trip management service                     | [charts/trips](../charts/trips/)                         |

## Development Services (dev)

| Service                 | Purpose                                            | Chart                                                                  |
| ----------------------- | -------------------------------------------------- | ---------------------------------------------------------------------- |
| **Claude**              | Claude Code deployment for AI-assisted development | [charts/claude](../charts/claude/)                                     |
| **Cloudflare Operator** | Custom operator for Cloudflare resource management | [charts/cloudflare-operator-test](../charts/cloudflare-operator-test/) |
| **Marine**              | Real-time AIS vessel tracking (ships.jomcgi.dev)   | [charts/marine](../charts/marine/)                                     |
| **OCI Model Cache**     | HuggingFace model caching operator                 | [operators/oci-model-cache](../operators/oci-model-cache/)             |
| **Stargazer**           | Experimental service sandbox                       | [charts/stargazer](../charts/stargazer/)                               |

## Static Websites

| Site                 | Description                                   |
| -------------------- | --------------------------------------------- |
| **jomcgi.dev**       | Personal website (Astro, Cloudflare Pages)    |
| **hikes.jomcgi.dev** | Hiking route finder (static, Cloudflare R2)   |
| **ships.jomcgi.dev** | Real-time vessel tracking UI (React/MapLibre) |
| **trips.jomcgi.dev** | Road trip tracker and photo viewer (Astro, Cloudflare Pages) |

## Service Details

For detailed information about specific services, see the README in each chart:

- `charts/<service>/README.md`

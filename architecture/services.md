# Services Overview

This document provides an overview of all services running in the cluster.

## Core Infrastructure (cluster-critical)

| Service | Purpose |
|---------|---------|
| **ArgoCD** | GitOps controller for declarative cluster management |
| **ArgoCD Image Updater** | Automatic image updates for ArgoCD-managed applications |
| **cert-manager** | X.509 certificate management (required by Linkerd) |
| **CoreDNS** | Cluster DNS resolution for Kubernetes services |
| **Linkerd** | Service mesh for automatic distributed tracing and mTLS |
| **Kyverno** | Policy engine with auto OTEL/Linkerd injection |
| **Longhorn** | Distributed persistent storage with automated backups |
| **NVIDIA GPU Operator** | GPU support for vLLM workloads |
| **SigNoz** | Self-hosted observability (metrics, logs, traces) |
| **1Password Operator** | Secret management via OnePasswordItem CRDs |

## Production Services (prod)

| Service | Purpose |
|---------|---------|
| **Cloudflare Tunnel** | Zero Trust ingress (no open firewall ports) |
| **gh-arc-controller** | GitHub Actions Runner Controller |
| **gh-arc-runners** | Self-hosted runners with Docker-in-Docker |
| **API Gateway** | External service routing with rate limiting |
| **NATS** | High-performance messaging with JetStream |
| **SeaweedFS** | Distributed S3-compatible object storage |
| **Trips** | Trip management service |
| **vLLM** | LLM inference server (Qwen3-Coder-30B-A3B) |

## Development Services (dev)

| Service | Purpose |
|---------|---------|
| **Claude** | Claude Code deployment for AI-assisted development |
| **Cloudflare Operator** | Custom operator for Cloudflare resource management |
| **Marine** | Real-time AIS vessel tracking (ships.jomcgi.dev) |
| **Stargazer** | Experimental service sandbox |

## Static Websites

| Site | Description |
|------|-------------|
| **jomcgi.dev** | Personal website (Astro, Cloudflare Pages) |
| **hikes.jomcgi.dev** | Hiking route finder (static, Cloudflare R2) |
| **ships.jomcgi.dev** | Real-time vessel tracking UI (React/MapLibre) |

## Service Details

For detailed information about specific services, see the README in each chart:
- `charts/<service>/README.md`

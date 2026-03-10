---
layout: home

hero:
  name: Homelab Docs
  text: Infrastructure & Architecture
  tagline: Documentation for jomcgi/homelab — a Kubernetes homelab managed with GitOps, Bazel, and ArgoCD.
  actions:
    - theme: brand
      text: Architecture
      link: /docs/services
    - theme: alt
      text: ADRs
      link: /docs/decisions/
    - theme: alt
      text: GitHub
      link: https://github.com/jomcgi/homelab

features:
  - title: GitOps with ArgoCD
    details: All cluster state is declarative. Changes go through Git — ArgoCD syncs automatically.
  - title: Bazel Monorepo
    details: Multi-language builds, hermetic container images with apko, and consistent tooling across Go, Python, and JS.
  - title: Observability
    details: OpenTelemetry auto-instrumentation with self-hosted SigNoz for traces, metrics, and logs.
  - title: Security
    details: Cloudflare Tunnels for ingress, Kyverno policies, 1Password for secrets, non-root containers.
---

[joe@jomcgi.dev](mailto:joe@jomcgi.dev) | [linkedin/jomcgi](https://www.linkedin.com/in/jomcgi/) | [github/jomcgi](https://github.com/jomcgi) | Vancouver
## Joe McGinley
Mostly I build tools and infrastructure that other engineers don't have to think about.

Based in Vancouver, originally from Scotland.

Senior Platform Engineer at Semgrep. I run multi-cluster Kubernetes on AWS - ArgoCD, CI/CD pipelines, OpenTelemetry instrumentation.

---
### Side Quests
* [trips.jomcgi.dev](https://trips.jomcgi.dev) - Road trip tracker for our upcoming Yukon drive. On-the-road inference to detect wildlife from a car-mounted GoPro.
* [Frank x Vancouver](https://jomcgi.dev/frank) - Trip website for my sister's visit.
* [hikes.jomcgi.dev](https://hikes.jomcgi.dev) - Find hikes in Scotland with good weather right now. Forecast updates every 30 minutes.

---

### Homelab
5-node Kubernetes cluster running in my office.

#### Current projects
* Stargazer - Map of good stargazing spots near me. Filters for road access, low light pollution, and clear forecasts.
* Sextant - generates typed Go for Kubernetes operators from declarative state machines. Control flow is visible, invalid transitions fail at compile time.
* Opencode WebUI - Self-hosted coding assistant. Sessions run as pods with access to multiple LLM backends (Anthropic, Google, local vLLM) and my full monorepo tooling.
* Cloudflare operator - make it easier to spin up new projects, this allows me to annotate a service with a domain and have the operator manage creating tunnels / forwarding traffic / creating DNS records / setting zero trust rules.


#### Architecture decisions
Monorepo for simplicity - I don't want to spread context / build processes across multiple repos.

Bazel - support building and deploying across multiple languages. Makes multiplatform image builds really easy with [apko](https://github.com/chainguard-dev/apko). Love that I can write a rule once and benefit from it for years.

Gitops - deploy to k8s using ArgoCD, mirror what I spend time maintaining at work and would work well if I ever setup multiple clusters.

Ingress - Cloudflare Tunnels running in-cluster managed by my k8s operator, zero trust policies enforce SSO requirements.

Policy enforcement - using Kyverno to prevent mistakes, this is just me so I'm not getting peer-reviews for changes.

Observability - otel autoinstrumentation where suitable, self-hosting [signoz](https://signoz.io/).

Storage - Longhorn for persistent volumes, generally avoiding state management where possible. Anything remotely critical is frequently backed up offsite.

Service Mesh - Linkerd for securing service to service communication and generating telemetry.

[github.com/jomcgi/homelab](https://github.com/jomcgi/homelab) (Making this public soon)

# Technology Stack

## Project Type
Cloud-native infrastructure platform - Kubernetes-based homelab with GitOps deployment, observability, and zero-trust networking.

## Core Technologies

### Primary Language(s)
- **Infrastructure as Code**: YAML/JSON for Kubernetes manifests, Helm templates, and Kustomize overlays
- **Scripting**: Bash for automation and operational tasks
- **Configuration**: HCL for potential Terraform usage (future)

### Key Dependencies/Libraries
- **Kubernetes**: v1.27+ - Container orchestration platform
- **Talos Linux**: v1.5+ - Immutable Kubernetes-focused operating system
- **ArgoCD**: v2.8+ - GitOps continuous deployment
- **Helm**: v3.12+ - Kubernetes package manager
- **Kustomize**: v5.0+ - Kubernetes configuration customization
- **Cloudflare Tunnel**: cloudflared - Zero-trust network access
- **Longhorn**: v1.5+ - Distributed block storage
- **1Password Operator**: v1.4+ - Secret management
- **SigNoz**: v0.40+ - OpenTelemetry-native observability platform

### Application Architecture
**GitOps-driven infrastructure** with:
- **Declarative configuration**: All infrastructure defined in Git repository
- **Automated reconciliation**: ArgoCD continuously syncs cluster state with Git
- **Immutable infrastructure**: Talos Linux nodes are immutable and configured via API
- **Microservices pattern**: Each service deployed independently with clear boundaries
- **Zero-trust networking**: No services exposed directly to internet; all ingress via Cloudflare Tunnel
- **Operator pattern**: Custom controllers (Cloudflare operator, 1Password operator) manage external resources

### Data Storage (if applicable)
- **Primary storage**: Longhorn distributed block storage with replication
- **Persistent volumes**: Dynamic provisioning via StorageClass
- **Backup storage**: Longhorn snapshots and backups (S3-compatible storage for disaster recovery)
- **Secret storage**: 1Password vaults (external, referenced via OnePasswordItem CRDs)
- **Configuration storage**: Git repository as single source of truth

### External Integrations (if applicable)
- **Cloudflare API**: DNS management, tunnel configuration, Zero Trust policies
- **1Password Connect API**: Secret synchronization and rotation
- **SigNoz**: Metrics, logs, and traces ingestion via OpenTelemetry Protocol (OTLP)
- **Protocols**: HTTP/HTTPS, gRPC, WebSocket, OTLP
- **Authentication**:
  - Cloudflare Access for external service authentication
  - Kubernetes RBAC for internal authorization
  - 1Password Connect tokens for secret access

### Monitoring & Dashboard Technologies (if applicable)
- **Observability Platform**: SigNoz (web-based, self-hosted)
- **Metrics Collection**: OpenTelemetry Collector with Prometheus receiver
- **Log Aggregation**: OpenTelemetry Collector with filelog receiver
- **Distributed Tracing**: OpenTelemetry SDK instrumentation
- **Real-time Communication**: SigNoz WebSocket for live data updates
- **Visualization**: SigNoz built-in dashboards, ClickHouse backend for queries
- **CLI Tools**: kubectl, k9s, helm for cluster inspection

## Development Environment

### Build & Development Tools
- **Build System**: Helm for templating, Kustomize for overlays, ArgoCD for deployment
- **Package Management**: Helm repositories, OCI registries for container images
- **Development workflow**:
  - Local testing with Minikube
  - Port-forwarding for service access during development
  - ArgoCD sync for production deployments
- **Container Registry**: Docker Hub, GitHub Container Registry (GHCR)

### Code Quality Tools
- **Static Analysis**:
  - `yamllint` for YAML syntax validation
  - `helm lint` for Helm chart validation
  - `kubeval` for Kubernetes manifest validation
  - `kube-linter` for security and best practices
- **Formatting**:
  - Consistent YAML indentation (2 spaces)
  - Helm chart conventions
- **Testing Framework**:
  - Helm unit tests (planned)
  - Integration tests with Minikube
  - Smoke tests via ArgoCD health checks
- **Documentation**: Inline comments in Helm templates, README.md per chart

### Version Control & Collaboration
- **VCS**: Git with GitHub
- **Branching Strategy**:
  - Feature branches for development
  - Main branch as production source of truth
  - Direct commits to main for small changes (single-person project)
- **Code Review Process**: Self-review before merge (single maintainer)

### Dashboard Development (if applicable)
- **SigNoz Development**: Not modified; consumed as-is via Helm chart
- **Access**: Via Cloudflare Tunnel or kubectl port-forward
- **Multi-Instance Support**: Single production instance, ephemeral test instances in Minikube

## Deployment & Distribution (if applicable)
- **Target Platform(s)**: Bare-metal Kubernetes cluster running Talos Linux on x86_64 hardware
- **Distribution Method**:
  - Infrastructure via Git repository (GitOps)
  - Container images from public registries
  - Helm charts from public/private repositories
- **Installation Requirements**:
  - Talos Linux installed on cluster nodes
  - kubectl access configured
  - ArgoCD bootstrapped manually
  - 1Password Operator bootstrapped with Connect token
- **Update Mechanism**:
  - Git commits trigger ArgoCD sync
  - Helm chart version updates in application manifests
  - Rolling updates for stateless services
  - StatefulSet updates with pod disruption budgets

## Technical Requirements & Constraints

### Performance Requirements
- **Service startup time**: <30 seconds for typical service
- **ArgoCD sync time**: <2 minutes for full cluster sync
- **Storage performance**: Longhorn provides 50+ MB/s read/write with replication
- **Network latency**: <100ms for intra-cluster communication
- **Observability overhead**: <5% CPU/memory impact from OpenTelemetry collection

### Compatibility Requirements
- **Platform Support**: Linux x86_64 only (Talos Linux requirement)
- **Kubernetes Version**: v1.27+ (tested on Talos Kubernetes distribution)
- **Helm Version**: v3.12+ (Helm 2 not supported)
- **Standards Compliance**:
  - Kubernetes API compatibility
  - OpenTelemetry Protocol (OTLP) specification
  - Prometheus metrics exposition format

### Security & Compliance
- **Security Requirements**:
  - All containers run non-root with read-only root filesystem
  - No privileged containers (except storage/networking infrastructure)
  - Network policies for pod-to-pod communication (where needed)
  - Secrets encrypted at rest in etcd
  - All external ingress via Cloudflare Tunnel (mTLS to cluster)
- **Compliance Standards**: Not applicable (personal homelab)
- **Threat Model**:
  - **Primary threat**: Internet exposure of services (mitigated via zero-trust networking)
  - **Secondary threat**: Container escapes (mitigated via seccomp, AppArmor, read-only filesystems)
  - **Accepted risk**: Physical access to hardware (home environment)

### Scalability & Reliability
- **Expected Load**: Low traffic (single-user homelab, <100 req/sec aggregate)
- **Availability Requirements**:
  - Target 99% uptime for critical services
  - Planned maintenance windows acceptable
  - No SLA (personal use)
- **Growth Projections**:
  - Scale to 10-20 services over time
  - Single-cluster deployment (no multi-cluster federation)
  - Horizontal scaling for stateless services as needed

## Technical Decisions & Rationale

### Decision Log

1. **Talos Linux over traditional Linux distributions**:
   - **Rationale**: Immutable OS designed for Kubernetes eliminates configuration drift, reduces attack surface, and simplifies operations
   - **Trade-offs**: Less flexibility for system-level customization, steeper learning curve for troubleshooting

2. **ArgoCD over other GitOps tools (Flux, Jenkins)**:
   - **Rationale**: ArgoCD provides excellent UI for visualizing deployments, strong community support, and handles both Helm and Kustomize natively
   - **Trade-offs**: Additional component to maintain, slight operational complexity vs. manual kubectl apply

3. **Cloudflare Tunnel over traditional ingress (nginx, Traefik)**:
   - **Rationale**: Zero-trust networking without exposing home network, DDoS protection, automatic HTTPS, built-in WAF
   - **Trade-offs**: Dependency on Cloudflare service availability, vendor lock-in for edge networking

4. **1Password Operator over Sealed Secrets or SOPS**:
   - **Rationale**: Secrets stored in trusted external system (1Password), automatic rotation capabilities, better separation of concerns
   - **Trade-offs**: External dependency, requires 1Password subscription, additional operator to maintain

5. **SigNoz over Grafana Cloud or Prometheus/Loki/Tempo stack**:
   - **Rationale**: Self-hosted observability with unified interface for metrics/logs/traces, OpenTelemetry-native, simpler than maintaining separate systems
   - **Trade-offs**: Higher resource usage than Grafana Cloud, requires ClickHouse storage, newer project with smaller community

6. **Longhorn over Rook/Ceph or NFS**:
   - **Rationale**: Kubernetes-native with simple deployment, good balance of features vs. complexity, excellent backup capabilities
   - **Trade-offs**: Performance lower than dedicated storage appliances, requires local disks on nodes

## Known Limitations

- **Single cluster deployment**: No multi-cluster federation or geographic distribution. Impact: Limited disaster recovery options beyond backups. Future: Could implement cross-cluster GitOps if scaling beyond single location.

- **Manual 1Password Operator bootstrap**: Requires manual installation with Connect token before GitOps can manage other secrets. Impact: Not fully declarative from bare metal. Exists because: Chicken-and-egg problem with secret management. Addressed: Document bootstrap procedure clearly.

- **Limited automated testing**: Integration tests exist but are not comprehensive. Impact: Risk of regressions when making infrastructure changes. Future: Expand test coverage with ephemeral cluster deployments in CI.

- **No multi-tenancy**: Single-user cluster with shared namespaces. Impact: Cannot safely isolate workloads for multiple users. Addressed: Not a current requirement; would need network policies and RBAC overhaul for multi-tenant support.

- **Cloudflare Tunnel dependency**: All external access requires Cloudflare service availability. Impact: Outage blocks external access (internal cluster still functional). Future: Could add VPN fallback for emergency access.

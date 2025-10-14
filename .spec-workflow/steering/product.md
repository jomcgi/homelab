# Product Overview

## Product Purpose
A security-first Kubernetes homelab running on Talos Linux that provides a production-grade infrastructure platform for self-hosted services with zero direct internet exposure. The platform enables safe experimentation with cloud-native technologies while maintaining operational simplicity and robust security guarantees.

## Target Users
**Primary User**: The homelab operator (technical individual running personal infrastructure)

**Needs and Pain Points**:
- Need to self-host services without exposing home network to internet
- Want production-grade security without enterprise complexity
- Require observable, debuggable infrastructure for learning and experimentation
- Need automated deployments that are easy to reason about
- Want to avoid configuration drift and manual intervention

## Key Features

1. **Zero Trust Network Access**: All external ingress flows through Cloudflare Tunnel with no open firewall ports, providing DDoS protection and WAF capabilities
2. **GitOps Deployment**: ArgoCD-managed deployments with automatic drift detection, self-healing, and declarative configuration
3. **Secure Secret Management**: 1Password operator integration with OnePasswordItem CRDs for credential storage and automatic secret synchronization
4. **Distributed Storage**: Longhorn persistent storage with automated backups and high availability
5. **Security by Default**: All containers run with read-only filesystems, non-root users, and capability dropping
6. **Infrastructure as Code**: Helm charts and Kustomize overlays for all services with version control

## Business Objectives

- **Learn cloud-native technologies** hands-on in a production-like environment
- **Host personal services securely** without relying on third-party SaaS providers
- **Maintain operational simplicity** that allows the platform to run with minimal intervention
- **Build deep understanding** of Kubernetes, security, and observability patterns
- **Create reusable patterns** that can be applied to professional work

## Success Metrics

- **Deployment Success Rate**: >95% of ArgoCD sync operations succeed without intervention
- **Security Posture**: Zero services with direct internet exposure, all containers running with security hardening
- **Service Availability**: >99% uptime for critical services (measured via health checks)
- **Time to Deploy New Service**: <30 minutes from idea to production-ready deployment
- **Incident Resolution Time**: <1 hour to identify and resolve issues via observability tools

## Product Principles

1. **Simplicity over Cleverness**: Complexity is the enemy of reliability. Every component should have a clear purpose with obvious behavior. Avoid clever solutions that are hard to understand or operate.

2. **Security by Default**: Services must be secure without additional configuration. All containers run non-root, use read-only filesystems, and have minimal privileges. Network access is zero-trust by default.

3. **Observable Everything**: If you can't measure it, you can't improve it. All services export metrics, provide health checks, and send structured logs. Observability is not optional.

4. **Deep Modules with Clean Interfaces**: Services should hide complex implementations behind simple, well-defined interfaces. Configuration should be minimal and obvious.

5. **Test Real Behavior**: Integration tests deploy actual services to test clusters and verify end-to-end functionality. Unit tests that mock everything provide false confidence.

## Monitoring & Visibility

- **Dashboard Type**: Web-based SigNoz dashboards and Kubernetes CLI tools (kubectl, k9s)
- **Real-time Updates**: OpenTelemetry collector streaming metrics, logs, and traces to SigNoz
- **Key Metrics Displayed**:
  - Service health status and uptime
  - Resource utilization (CPU, memory, disk)
  - ArgoCD sync status and deployment health
  - Network traffic and connection counts
  - Application-specific business metrics
  - Distributed traces for request flows
- **Sharing Capabilities**: Read-only SigNoz dashboard links for sharing observability data

## Future Vision

### Potential Enhancements
- **Remote Access**: Expand Cloudflare Tunnel usage to enable secure remote access for family members to specific services (photo sharing, document storage)
- **Analytics**: Historical performance analysis, capacity planning dashboards, and trend detection for resource usage
- **Collaboration**: Multi-tenant capabilities for running services for multiple users with proper isolation
- **Advanced Observability**: Comprehensive distributed tracing across all services, SLO tracking and alerting, custom metrics dashboards
- **Automated Testing**: Continuous integration pipeline that deploys to ephemeral test clusters and runs full integration test suites
- **Disaster Recovery**: Automated backup testing, documented recovery procedures, and infrastructure recreation from code

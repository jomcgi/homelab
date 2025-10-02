# Implementation Plan

## Task Overview
This implementation creates the Obsidian Automation service following a hybrid architecture with browser automation for authentication and REST API for operations. Tasks are organized by component and follow atomic principles for optimal agent execution.

## Steering Document Compliance
Tasks follow structure.md conventions with proper Helm chart organization in `charts/obsidian-automation/` and ArgoCD application in `clusters/homelab/obsidian-automation/`. Security context and observability patterns align with tech.md standards.

## Atomic Task Requirements
**Each task must meet these criteria for optimal agent execution:**
- **File Scope**: Touches 1-3 related files maximum
- **Time Boxing**: Completable in 15-30 minutes
- **Single Purpose**: One testable outcome per task
- **Specific Files**: Must specify exact files to create/modify
- **Agent-Friendly**: Clear input/output with minimal context switching

## Task Format Guidelines
- Use checkbox format: `- [ ] Task number. Task description`
- **Specify files**: Always include exact file paths to create/modify
- **Include implementation details** as bullet points
- Reference requirements using: `_Requirements: X.Y, Z.A_`
- Reference existing code to leverage using: `_Leverage: path/to/file.ts, path/to/component.tsx_`
- Focus only on coding tasks (no deployment, user testing, etc.)
- **Avoid broad terms**: No "system", "integration", "complete" in task titles

## Good vs Bad Task Examples
❌ **Bad Examples (Too Broad)**:
- "Implement authentication system" (affects many files, multiple purposes)
- "Add user management features" (vague scope, no file specification)
- "Build complete dashboard" (too large, multiple components)
- "Configure all security settings" (multiple security contexts)

✅ **Good Examples (Atomic)**:
- "Create OnePasswordItem CRD in templates/onepassworditem.yaml"
- "Add readiness probe configuration to StatefulSet in statefulset.yaml"
- "Configure Prometheus metrics endpoint in monitor/main.go"
- "Set container security context with read-only filesystem in statefulset.yaml"

## Tasks

### 1. Helm Chart Foundation

- [x] 1. Create Helm chart structure in charts/obsidian-automation/Chart.yaml
  - File: charts/obsidian-automation/Chart.yaml
  - Create chart metadata with obsidian-automation name and description
  - Set version 1.0.0, appVersion matching Obsidian version
  - Add maintainer information following homelab pattern
  - Purpose: Establish Helm chart foundation for deployment
  - _Leverage: charts/n8n/Chart.yaml, charts/cloudflare-tunnel/Chart.yaml_
  - _Requirements: 9.5_

- [x] 2. Create base values configuration in charts/obsidian-automation/values.yaml
  - File: charts/obsidian-automation/values.yaml
  - Define default resource limits (2GB RAM, 2 CPU cores)
  - Configure storage specifications for vault/config/session volumes
  - Set security context with non-root user, read-only filesystem
  - Purpose: Provide default configuration values for all environments
  - _Leverage: charts/n8n/values.yaml_
  - _Requirements: 8.1, 8.2, 9.1, 9.5_

- [x] 3. Create production values override in charts/obsidian-automation/values.prod.yaml
  - File: charts/obsidian-automation/values.prod.yaml
  - Override resource limits for production workload
  - Configure Longhorn storage class and sizes
  - Set production-specific monitoring and logging levels
  - Purpose: Environment-specific configuration for production deployment
  - _Leverage: overlays/prod/n8n/values.yaml_
  - _Requirements: 9.1, 9.5_

### 2. 1Password Integration

- [x] 4. Create OnePasswordItem template in charts/obsidian-automation/templates/onepassworditem.yaml
  - File: charts/obsidian-automation/templates/onepassworditem.yaml
  - Define OnePasswordItem CRD for Obsidian Sync credentials
  - Reference vault path for email and password fields
  - Configure secret generation with appropriate data keys
  - Purpose: Secure credential management via 1Password Operator
  - _Leverage: operators/cloudflare/helm/cloudflare-operator/examples/1password-secret.yaml_
  - _Requirements: 7.1, 7.2_

### 3. StatefulSet and Storage

- [x] 5. Create StatefulSet template in charts/obsidian-automation/templates/statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml
  - Define StatefulSet with single replica for session persistence
  - Configure volumeClaimTemplates for vault-data, config-data, session-data
  - Add metadata labels following homelab conventions
  - Purpose: Core deployment manifest with persistent storage
  - _Leverage: structure.md labels/annotations patterns_
  - _Requirements: 3.3, 9.1, 9.5_

- [x] 6. Add initContainer for Playwright authentication to statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Configure Playwright initContainer with Microsoft image
  - Mount session volume and authentication scripts
  - Set environment variables from 1Password secret
  - Purpose: Handle one-time authentication before main container starts
  - _Leverage: existing initContainer patterns from research_
  - _Requirements: 1.1, 1.3, 1.4_

- [x] 7a. Configure Obsidian container image and ports in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Add Obsidian container with LinuxServer image
  - Configure container ports 3001 (web UI) and 27124 (REST API)
  - Set container name and image pull policy
  - Purpose: Define basic Obsidian container configuration
  - _Leverage: container patterns from existing StatefulSets_
  - _Requirements: 2.1_

- [x] 7b. Add volume mounts for persistent storage in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Mount vault-data volume to /vaults path
  - Mount config-data volume to /config path
  - Mount session-data volume to /config/.config/obsidian path
  - Purpose: Enable persistent storage for Obsidian data
  - _Leverage: volume mount patterns from charts/n8n_
  - _Requirements: 3.3, 9.5_

- [x] 7c. Apply security context to Obsidian container in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Set runAsNonRoot: true, runAsUser: 1000, fsGroup: 1000
  - Configure readOnlyRootFilesystem: true with tmpfs mounts
  - Drop all capabilities and disable privilege escalation
  - Purpose: Implement security best practices for container
  - _Leverage: security context from structure.md_
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 8a. Add sync monitor sidecar container configuration in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Add sync-monitor container with custom Go image
  - Configure container ports 8080 for metrics endpoint
  - Set container name and image references
  - Purpose: Add monitoring sidecar to pod specification
  - _Leverage: sidecar patterns from existing deployments_
  - _Requirements: 5.1, 5.3_

- [ ] 8b. Configure resource limits and environment for sync monitor in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Set resource limits: 256Mi memory, 200m CPU
  - Set resource requests: 128Mi memory, 100m CPU
  - Add environment variables for API endpoint and key references
  - Purpose: Control resource usage and configure monitoring
  - _Leverage: resource patterns from existing sidecars_
  - _Requirements: 9.1_

- [ ] 8c. Add health and readiness probes for sync monitor in statefulset.yaml
  - File: charts/obsidian-automation/templates/statefulset.yaml (modify existing)
  - Configure readinessProbe on /ready endpoint with appropriate delays
  - Configure livenessProbe on /health endpoint with failure thresholds
  - Set probe timeouts and intervals for sync monitoring
  - Purpose: Enable Kubernetes health monitoring for sync status
  - _Leverage: probe patterns from existing services_
  - _Requirements: 5.4, 6.1_

### 4. Services and Networking

- [x] 9. Create Service template in charts/obsidian-automation/templates/service.yaml
  - File: charts/obsidian-automation/templates/service.yaml
  - Expose REST API port 27124 and metrics port 8080
  - Configure ClusterIP service for internal cluster access
  - Add service discovery labels and annotations
  - Purpose: Enable internal cluster access to API and metrics
  - _Leverage: existing service templates from other charts_
  - _Requirements: 2.1, 2.4_

- [x] 10. Create NetworkPolicy template in charts/obsidian-automation/templates/networkpolicy.yaml
  - File: charts/obsidian-automation/templates/networkpolicy.yaml
  - Define ingress rules for Cloudflare Tunnel and metrics scraping
  - Configure egress rules for DNS, Obsidian Sync, and 1Password operator
  - Apply zero-trust network security model
  - Purpose: Enforce network-level security controls
  - _Leverage: network policy patterns from security documentation_
  - _Requirements: 8.5, 8.6_

### 5. Authentication Scripts

- [x] 11. Create ConfigMap for authentication scripts in charts/obsidian-automation/templates/configmap.yaml
  - File: charts/obsidian-automation/templates/configmap.yaml
  - Define Playwright authentication script in JavaScript
  - Include session persistence and API validation logic
  - Add error handling and retry mechanisms
  - Purpose: Package authentication automation scripts
  - _Leverage: configMap patterns from existing charts_
  - _Requirements: 1.1, 1.2, 3.1, 3.4_

- [x] 12. Create authentication script logic in configmap.yaml data section
  - File: charts/obsidian-automation/templates/configmap.yaml (modify existing)
  - Implement Playwright script for Obsidian web UI login
  - Add session state persistence to /session volume
  - Include REST API availability verification
  - Purpose: Actual authentication implementation
  - _Leverage: Playwright patterns for headless browser automation_
  - _Requirements: 1.1, 1.3, 3.2_

### 6. Monitoring and Observability

- [x] 13. Create ServiceMonitor template in charts/obsidian-automation/templates/servicemonitor.yaml
  - File: charts/obsidian-automation/templates/servicemonitor.yaml
  - Configure Prometheus scraping for metrics port 8080
  - Set scrape interval and timeout appropriate for sync monitoring
  - Add metric labels for service identification
  - Purpose: Enable Prometheus metrics collection
  - _Leverage: ServiceMonitor patterns from existing services_
  - _Requirements: 5.5, observability from tech.md_

- [x] 14. Create sync monitor application structure in charts/obsidian-automation/monitor/
  - Files: charts/obsidian-automation/monitor/main.go, monitor/go.mod
  - Initialize Go module for sync monitoring sidecar
  - Create basic HTTP server for health and metrics endpoints
  - Add Prometheus client library dependency
  - Purpose: Foundation for sync monitoring implementation
  - _Leverage: Go patterns from existing operators_
  - _Requirements: 5.1, 5.3, observability requirements_

- [x] 15a. Add REST API client for Obsidian communication in monitor/main.go
  - File: charts/obsidian-automation/monitor/main.go (modify existing)
  - Create HTTP client with proper authentication headers
  - Add functions for GET/POST requests to Obsidian REST API
  - Include error handling and timeout configuration
  - Purpose: Enable communication with Obsidian REST API
  - _Leverage: HTTP client patterns from Go standard library_
  - _Requirements: 5.1, 6.1_

- [ ] 15b. Implement 5-minute synthetic test logic in monitor/main.go
  - File: charts/obsidian-automation/monitor/main.go (modify existing)
  - Create ticker for 5-minute intervals
  - Implement test note creation, verification, and deletion cycle
  - Add test failure tracking and logging
  - Purpose: Continuously verify sync functionality
  - _Leverage: Go ticker patterns and error tracking_
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 15c. Add Prometheus metrics export for sync status in monitor/main.go
  - File: charts/obsidian-automation/monitor/main.go (modify existing)
  - Define sync_connected, sync_last_success, and api_request_duration metrics
  - Export metrics on /metrics endpoint using prometheus/client_golang
  - Update metrics based on synthetic test results
  - Purpose: Expose sync status for monitoring and alerting
  - _Leverage: Prometheus client patterns from existing Go services_
  - _Requirements: 5.5, observability requirements_

### 7. Session Maintenance

- [x] 16. Create CronJob template in charts/obsidian-automation/templates/cronjob.yaml
  - File: charts/obsidian-automation/templates/cronjob.yaml
  - Configure CronJob to run every 6 hours for session validation
  - Use curl image to check REST API health endpoint
  - Add pod deletion logic when API check fails
  - Purpose: Automated session maintenance and re-authentication trigger
  - _Leverage: CronJob patterns from cluster maintenance_
  - _Requirements: 4.1, 4.2, 4.3_

### 8. RBAC and Security

- [x] 17. Create ServiceAccount template in charts/obsidian-automation/templates/serviceaccount.yaml
  - File: charts/obsidian-automation/templates/serviceaccount.yaml
  - Define service account for CronJob pod management operations
  - Add appropriate labels and annotations
  - Configure automountServiceAccountToken as needed
  - Purpose: Enable CronJob to delete pods for re-authentication
  - _Leverage: ServiceAccount patterns from existing deployments_
  - _Requirements: 4.2_

- [x] 18. Create RBAC templates in charts/obsidian-automation/templates/rbac.yaml
  - File: charts/obsidian-automation/templates/rbac.yaml
  - Define Role with pod deletion permissions in namespace
  - Create RoleBinding linking ServiceAccount to Role
  - Follow principle of least privilege for permissions
  - Purpose: Grant minimal required permissions for pod management
  - _Leverage: RBAC patterns from operators/cloudflare_
  - _Requirements: 4.2, security best practices_

### 9. ArgoCD Application

- [ ] 19. Create ArgoCD application directory structure
  - Files: clusters/homelab/obsidian-automation/application.yaml
  - Create directory following existing ArgoCD application patterns
  - Add .gitkeep if needed for empty directory structure
  - Purpose: Prepare ArgoCD deployment configuration
  - _Leverage: clusters/homelab/cloudflare-tunnel/ structure_
  - _Requirements: GitOps workflow from tech.md_

- [ ] 20. Create ArgoCD Application manifest in clusters/homelab/obsidian-automation/application.yaml
  - File: clusters/homelab/obsidian-automation/application.yaml
  - Configure Application pointing to charts/obsidian-automation
  - Set automated sync with prune and self-heal enabled
  - Add extended health check timeout for initContainer authentication
  - Purpose: Enable GitOps deployment via ArgoCD
  - _Leverage: clusters/homelab/cloudflare-tunnel/application.yaml_
  - _Requirements: GitOps deployment, automated management_

- [ ] 21. Create production value overrides in clusters/homelab/obsidian-automation/values.yaml
  - File: clusters/homelab/obsidian-automation/values.yaml
  - Override default values for production environment
  - Configure specific 1Password vault references
  - Set production resource limits and storage sizes
  - Purpose: Environment-specific configuration for production cluster
  - _Leverage: clusters/homelab/cloudflare-tunnel/values.yaml_
  - _Requirements: 9.1, 9.5, production deployment_

### 10. Container Images and Build

- [ ] 22a. Create multi-stage Dockerfile build setup in charts/obsidian-automation/monitor/Dockerfile
  - File: charts/obsidian-automation/monitor/Dockerfile
  - Set up Go build stage with official golang image
  - Configure build arguments and workdir for compilation
  - Add go mod download and go build steps
  - Purpose: Establish efficient container build process
  - _Leverage: Go multi-stage patterns from existing operators_
  - _Requirements: container building best practices_

- [ ] 22b. Configure minimal runtime image in monitor/Dockerfile
  - File: charts/obsidian-automation/monitor/Dockerfile (modify existing)
  - Use distroless or alpine base image for minimal attack surface
  - Copy only the compiled binary from build stage
  - Set non-root user (UID 1000) for container execution
  - Purpose: Create secure, minimal runtime container
  - _Leverage: distroless patterns and security hardening_
  - _Requirements: 8.3, minimal container footprint_

- [ ] 23. Create GitHub Actions workflow in .github/workflows/obsidian-automation.yml
  - File: .github/workflows/obsidian-automation.yml
  - Configure workflow to build and push sync monitor image
  - Add container image scanning and security checks
  - Trigger on changes to obsidian-automation chart or monitor code
  - Purpose: Automated container image building and publishing
  - _Leverage: existing GitHub Actions workflows_
  - _Requirements: CI/CD automation, container registry_

### 11. Testing and Validation

- [ ] 24a. Create Helm chart rendering tests in charts/obsidian-automation/tests/integration_test.go
  - File: charts/obsidian-automation/tests/integration_test.go
  - Test chart rendering with default and custom values
  - Validate YAML output contains expected Kubernetes resources
  - Check template variable substitution works correctly
  - Purpose: Ensure Helm templates render valid Kubernetes manifests
  - _Leverage: Helm testing patterns from existing chart tests_
  - _Requirements: chart validation testing_

- [ ] 24b. Add Kubernetes resource validation tests in integration_test.go
  - File: charts/obsidian-automation/tests/integration_test.go (modify existing)
  - Validate StatefulSet has correct volumes and containers
  - Check Service selectors match StatefulSet labels
  - Verify RBAC permissions are properly configured
  - Purpose: Ensure Kubernetes resources are correctly related
  - _Leverage: resource validation patterns from existing tests_
  - _Requirements: integration testing from design_

- [ ] 24c. Add service endpoint health check tests in integration_test.go
  - File: charts/obsidian-automation/tests/integration_test.go (modify existing)
  - Test REST API endpoint accessibility (port 27124)
  - Verify metrics endpoint returns Prometheus format (port 8080)
  - Check health and readiness probe endpoints respond correctly
  - Purpose: Validate service endpoints are accessible after deployment
  - _Leverage: endpoint testing patterns and HTTP client testing_
  - _Requirements: end-to-end testing from design_

### 12. Documentation and Finalization

- [ ] 25. Create README.md with deployment and usage instructions
  - File: charts/obsidian-automation/README.md
  - Document installation via ArgoCD and direct Helm
  - Include API usage examples and troubleshooting guide
  - Add monitoring and observability information
  - Purpose: Enable others to deploy and operate the service
  - _Leverage: README patterns from existing charts_
  - _Requirements: usability requirements, documentation standards_
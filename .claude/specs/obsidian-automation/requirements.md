# Requirements Document

## Introduction

This feature implements an automated Obsidian service on Kubernetes that provides programmatic access to note creation and editing through a hybrid architecture. The solution uses browser automation for one-time authentication with Obsidian Sync, then exposes a REST API for ongoing operations. This enables automated note-taking workflows while maintaining full compatibility with Obsidian's official sync service.

## Alignment with Product Vision

This feature directly supports the homelab's objectives as outlined in product.md:

- **Service Hosting**: Provides a reliable platform for the planned "Obsidian Server" service with official sync integration
- **Learning Platform**: Demonstrates advanced Kubernetes patterns including StatefulSets, initContainers, and CronJobs
- **Observability**: Includes comprehensive health checks and metrics for the automation service
- **Experimentation**: Enables easy deployment of AI-powered note automation workflows
- **Simplicity**: Uses a clever hybrid approach that minimizes complexity while maximizing functionality

The feature aligns with the "Obsidian Sync" integration planned in the product roadmap and enables the "Plugin for API exposure to automate note interactions" mentioned in the planned services.

## Requirements

### Requirement 1: Automated Authentication

**User Story:** As a developer, I want the Obsidian service to automatically authenticate with Obsidian Sync on pod startup, so that I don't need to manually login each time the service restarts.

#### Acceptance Criteria

1. WHEN the Obsidian pod starts THEN the system SHALL automatically authenticate using stored credentials from 1Password
2. IF authentication fails THEN the system SHALL retry up to 3 times with exponential backoff
3. WHEN authentication succeeds THEN the system SHALL verify that the REST API plugin is available and responding
4. IF the REST API plugin is not available after sync THEN the system SHALL fail the pod startup with a clear error message

### Requirement 2: REST API Access

**User Story:** As a developer, I want to access Obsidian's REST API from other services in the cluster, so that I can programmatically create and edit notes.

#### Acceptance Criteria

1. WHEN the Obsidian service is running THEN the REST API SHALL be accessible on port 27124 within the cluster
2. IF an API request is made without proper authorization THEN the system SHALL return a 401 Unauthorized response
3. WHEN a valid API request is made THEN the system SHALL process it and trigger Obsidian Sync for the changes
4. IF the API becomes unresponsive THEN the readiness probe SHALL mark the pod as not ready

### Requirement 3: Session Persistence

**User Story:** As a developer, I want authentication sessions to persist across pod restarts, so that re-authentication is only needed when sessions expire.

#### Acceptance Criteria

1. WHEN the pod restarts with a valid session THEN the system SHALL reuse the existing session without re-authentication
2. IF a session expires THEN the system SHALL automatically trigger re-authentication
3. WHEN session data is stored THEN it SHALL be persisted in a Longhorn volume mounted at /session
4. IF session validation fails THEN the system SHALL clear the session and perform fresh authentication

### Requirement 4: Automatic Re-authentication

**User Story:** As a developer, I want the system to automatically re-authenticate when sessions expire, so that the service remains available without manual intervention.

#### Acceptance Criteria

1. WHEN a CronJob runs every 6 hours THEN it SHALL check if the REST API is responsive
2. IF the API check fails THEN the system SHALL delete the pod to trigger re-authentication
3. WHEN re-authentication is triggered THEN it SHALL follow the same process as initial authentication
4. IF re-authentication fails repeatedly THEN the system SHALL alert via metrics/logs

### Requirement 5: Sync Status Monitoring

**User Story:** As a developer, I want continuous verification that Obsidian Sync is connected and functioning, so that I know immediately if notes are failing to synchronize.

#### Acceptance Criteria

1. WHEN the service is running THEN it SHALL check sync status every 5 minutes via synthetic test
2. IF sync is disconnected THEN the system SHALL expose a metric indicating sync failure
3. WHEN a synthetic test runs THEN it SHALL create a test note, verify it syncs, and delete it
4. IF the synthetic test fails THEN the readiness probe SHALL mark the pod as not ready after 3 consecutive failures
5. WHEN sync status changes THEN the system SHALL log the event with timestamp and reason
6. IF sync has been disconnected for more than 15 minutes THEN the system SHALL trigger pod restart for re-authentication

### Requirement 6: Sync Verification API

**User Story:** As a developer, I want to query the current sync status through the API, so that I can verify synchronization before critical operations.

#### Acceptance Criteria

1. WHEN `/api/sync/status` is called THEN it SHALL return current sync connection status, last sync time, and pending changes count
2. IF sync is not connected THEN the endpoint SHALL return status 503 with details about the disconnection
3. WHEN `/api/sync/verify` is called THEN it SHALL perform an immediate sync check and return the result
4. IF there are pending unsynced changes THEN the API SHALL include a list of affected files

### Requirement 7: Secure Credential Management

**User Story:** As a security-conscious developer, I want Obsidian credentials to be securely managed, so that sensitive information is never exposed in the codebase.

#### Acceptance Criteria

1. WHEN credentials are needed THEN they SHALL be retrieved from 1Password using OnePasswordItem CRDs
2. IF credentials are not available THEN the pod SHALL fail to start with a clear error message
3. WHEN credentials are used THEN they SHALL only be available to the authentication container
4. IF credential rotation occurs in 1Password THEN the system SHALL use the updated credentials on next authentication

### Requirement 8: Container Security

**User Story:** As a security engineer, I want the Obsidian service to follow security best practices, so that it maintains the cluster's security posture while handling necessary write operations.

#### Acceptance Criteria

1. WHEN the Obsidian container runs THEN it SHALL use a read-only root filesystem with specific volume mounts for writable paths
2. IF write access is needed THEN it SHALL be limited to /vaults (notes), /config (Obsidian config), and /session (auth data) via mounted volumes
3. WHEN the container starts THEN it SHALL run as non-root user (UID 1000) with all capabilities dropped
4. IF privilege escalation is attempted THEN the security context SHALL prevent it
5. WHEN network access is configured THEN ingress SHALL only be allowed through Cloudflare Tunnel
6. IF direct internet exposure is attempted THEN network policies SHALL block it

### Requirement 9: Resource Management

**User Story:** As a cluster administrator, I want the Obsidian service to use resources efficiently, so that it doesn't impact other services in the cluster.

#### Acceptance Criteria

1. WHEN the Obsidian container runs THEN it SHALL be limited to 2GB RAM and 2 CPU cores
2. IF resource limits are exceeded THEN Kubernetes SHALL throttle or restart the pod as appropriate
3. WHEN Playwright runs for authentication THEN it SHALL complete within 60 seconds or timeout
4. IF authentication takes longer than 60 seconds THEN the initContainer SHALL fail and retry
5. WHEN storage is allocated THEN it SHALL use Longhorn with appropriate size limits (10Gi for vaults, 1Gi for config/session)

### Requirement 10: Failure Recovery

**User Story:** As a developer, I want the service to gracefully handle various failure scenarios, so that it can recover automatically without data loss.

#### Acceptance Criteria

1. WHEN Longhorn storage becomes unavailable THEN the pod SHALL enter a waiting state until storage recovers
2. IF a partial sync failure occurs THEN the system SHALL log affected files and retry sync for failed items only
3. WHEN the REST API plugin becomes corrupted THEN the system SHALL detect via health checks and trigger pod restart
4. IF network partition occurs between pod and Obsidian Sync THEN the system SHALL queue changes locally and retry when connection restored
5. WHEN sync conflicts are detected THEN the system SHALL preserve both versions and log the conflict for manual resolution

## Non-Functional Requirements

### Performance
- REST API response time SHALL be under 500ms for standard operations
- Authentication process SHALL complete within 60 seconds
- Sync operations SHALL not block API responses
- The service SHALL handle at least 10 concurrent API requests
- Sync status checks SHALL complete within 10 seconds

### Security
- All credentials SHALL be managed through 1Password Operator using OnePasswordItem CRDs
- The container SHALL run with the following security context:
  - runAsNonRoot: true
  - runAsUser: 1000
  - fsGroup: 1000
  - readOnlyRootFilesystem: true
  - allowPrivilegeEscalation: false
  - capabilities.drop: [ALL]
  - seccompProfile.type: RuntimeDefault
- Network access SHALL be restricted to ports 3001 (web UI) and 27124 (REST API)
- Ingress SHALL only be allowed through Cloudflare Tunnel
- API keys SHALL be rotated monthly and stored in 1Password
- Session data SHALL be encrypted at rest using Longhorn encryption

### Reliability
- The service SHALL automatically recover from transient failures
- Health checks SHALL accurately reflect service availability
- The service SHALL maintain 99% availability within the cluster
- Sync conflicts SHALL be handled gracefully without data loss
- Sync disconnections SHALL be detected within 5 minutes
- The service SHALL maintain sync connectivity 99.5% of the time
- Storage failures SHALL not cause data loss (graceful degradation)

### Observability
- The following Prometheus metrics SHALL be exposed on /metrics endpoint:
  - `obsidian_sync_connected` (gauge): 1 if connected, 0 if disconnected
  - `obsidian_sync_last_success_timestamp` (gauge): Unix timestamp of last successful sync
  - `obsidian_api_request_duration_seconds` (histogram): API response times
  - `obsidian_api_requests_total` (counter): Total API requests by endpoint and status
  - `obsidian_synthetic_test_success` (gauge): 1 if last synthetic test passed, 0 if failed
- All logs SHALL be structured JSON with the following fields:
  - timestamp, level, message, trace_id, span_id, component
- OpenTelemetry tracing SHALL be implemented for API requests with spans for:
  - Authentication, API processing, sync operations, storage operations
- All sync failures SHALL include: timestamp, affected files, error details, retry count
- Authentication events SHALL be logged with: timestamp, success/failure, reason

### Usability
- API documentation SHALL be available via OpenAPI/Swagger specification
- Error messages SHALL include: error code, user-friendly message, remediation steps
- The service SHALL integrate with existing homelab services via standard Kubernetes patterns
- Deployment SHALL follow standard ArgoCD GitOps workflow with Helm charts
- Sync status SHALL be queryable via:
  - REST API endpoint: GET /api/sync/status
  - Prometheus metrics: obsidian_sync_connected
  - Kubernetes readiness probe
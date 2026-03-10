# Cloudflare Operator Rewrite Using Sextant

## Overview

Rewrite the Cloudflare operator's 6 controllers using sextant state machine code generation to replace imperative reconciliation code with declarative state machines.

| Controller             | CRD Owner              | Phase Storage     | Approach                               |
| ---------------------- | ---------------------- | ----------------- | -------------------------------------- |
| CloudflareTunnel       | Us                     | Status.Phase      | Sextant generated                      |
| CloudflareAccessPolicy | Us                     | Status.Phase      | Sextant generated                      |
| Gateway                | Gateway API (external) | Annotation        | Manual state machine                   |
| HTTPRoute              | Gateway API (external) | Annotation        | Manual state machine                   |
| GatewayClass           | Gateway API (external) | Status.Conditions | Keep simple (validation only)          |
| Service                | N/A (helper)           | N/A               | Keep simple (annotation-based routing) |

**Key Constraint**: Gateway/HTTPRoute/GatewayClass are external Gateway API types - we cannot add `Status.Phase` fields. Use annotation-based phase storage for Gateway/HTTPRoute.

---

## Design Principles

### Error Handling Policy

All controllers must implement consistent error handling:

**Error Classification:**
| Error Type | Examples | Action |
|------------|----------|--------|
| Transient | API 500, timeout, rate limit (429) | Retry with backoff |
| Permanent | Invalid config, 403 (unauthorized) | Move to Failed, no retry |
| Conflict | Resource already exists (409) | Treat as success (idempotent) |

**Context-Aware 404 Handling:**
| Operation | 404 Meaning | Action |
|-----------|-------------|--------|
| Create (check if exists) | Resource doesn't exist yet | Proceed with creation (expected) |
| Get (during Ready) | Resource deleted externally | Transition to CreatingTunnel (recreate) |
| Update | Resource doesn't exist | Transition to CreatingTunnel (recreate) |
| Delete | Already deleted | Treat as success (idempotent) |

**Exponential Backoff:**

```
Base: 5s
Multiplier: 2x
Max: 5m
Jitter: ±10%

Sequence: 5s → 10s → 20s → 40s → 80s → 160s → 300s (cap)
```

**Retry Limits:**

- Transient errors: Max 10 retries before moving to Failed
- Failed state requeue: 1 hour (allows manual intervention)
- `RetryCount` resets on successful state transition

**Circuit Breaker (future consideration):**

- If >50% of reconciliations fail in 5 minutes, pause reconciliation for 1 minute
- Prevents cascading failures during Cloudflare outages
- **Interim Step**: Implement `golang.org/x/time/rate` limiter in Reconciler struct to respect global API limits.

---

### Spec Change Handling

When a resource spec changes while in `Ready` state:

**Detection:**

- Compare `status.observedGeneration` vs `metadata.generation`
- If different, spec has changed since last reconciliation

**Behavior:**

```
Ready (observedGeneration != generation) → Re-evaluate
  ├── If ingress config changed → ConfiguringIngress
  ├── If tunnel name changed → CreatingTunnel (recreate)
  └── If no material change → Stay Ready, update observedGeneration
```

**Implementation:**

- `VisitReady` checks generation mismatch
- Determines which fields changed
- Transitions to appropriate state for incremental update
- Avoids unnecessary Cloudflare API calls

---

### Deletion Handling

Deletion (via `deletionTimestamp`) must be handled from ANY non-terminal state:

**CloudflareTunnel:**

```
ANY STATE + deletionTimestamp → DeletingTunnel → Deleted
```

| From State         | Cleanup Required                       |
| ------------------ | -------------------------------------- |
| Pending            | None - just remove finalizer           |
| CreatingTunnel     | Delete tunnel if tunnelID exists       |
| CreatingSecret     | Delete tunnel + secret                 |
| ConfiguringIngress | Delete tunnel + secret                 |
| Ready              | Delete tunnel + secret                 |
| Failed             | Delete tunnel + secret (if they exist) |

**Implementation:**

- Every `Visit*` method checks `deletionTimestamp` first
- If set, transition to appropriate deletion state
- Deletion states are idempotent (safe to retry)

**CloudflareAccessPolicy:**

```
ANY STATE + deletionTimestamp → DeletingPolicies → DeletingApplication → Deleted
```

**Gateway/HTTPRoute:**

- Use OwnerReferences for cascading deletion
- Finalizer only needed for external Cloudflare resources (DNS records)

---

### Observability Requirements

**Metrics (Prometheus):**
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cloudflare_operator_reconcile_total` | Counter | controller, result | Total reconciliations |
| `cloudflare_operator_reconcile_duration_seconds` | Histogram | controller, phase | Reconcile latency |
| `cloudflare_operator_resource_phase` | Gauge | controller, namespace, name, phase | Current phase (1 = in this phase). **NOTE**: High cardinality if >100k resources. |
| `cloudflare_operator_errors_total` | Counter | controller, error_type | Errors by type |
| `cloudflare_operator_cloudflare_api_duration_seconds` | Histogram | operation | Cloudflare API latency |
| `cloudflare_operator_cloudflare_api_errors_total` | Counter | operation, status_code | Cloudflare API errors |

**Alerts:**
| Alert | Condition | Severity |
|-------|-----------|----------|
| `CloudflareOperatorHighErrorRate` | error_rate > 10% for 5m | Warning |
| `CloudflareOperatorReconcileStuck` | resource in non-terminal state > 30m | Warning |
| `CloudflareOperatorDown` | no reconciliations for 5m | Critical |
| `CloudflareAPIHighLatency` | p99 > 10s for 5m | Warning |

**Tracing:**

- Span per reconciliation with phase transitions as events
- Span per Cloudflare API call
- Trace context propagated through all operations

**Logging:**

- Structured JSON logs
- Required fields: `controller`, `namespace`, `name`, `phase`, `generation`
- Log level: INFO for state transitions, WARN for retries, ERROR for failures

---

### Annotation-Based Phase Storage (Gateway/HTTPRoute)

Gateway and HTTPRoute are external Gateway API types. Phase must be stored in annotations.

**Annotation Schema:**

```yaml
metadata:
  annotations:
    cloudflare.tunnels.io/phase: "Ready"
    cloudflare.tunnels.io/tunnel-id: "abc123"
    cloudflare.tunnels.io/retry-count: "0"
    cloudflare.tunnels.io/error-message: ""
```

**Validation Requirements:**

- `getPhase()` must validate annotation value against known phases
- Invalid/missing annotation → return `Pending` (not Unknown, to avoid infinite loops)
- Log warning when invalid phase detected
- Never trust user-editable annotations without validation

**Implementation:**

```go
func getGatewayPhase(gw *gatewayv1.Gateway) string {
    phase := gw.Annotations["cloudflare.tunnels.io/phase"]
    if !isValidGatewayPhase(phase) {
        log.Info("Invalid or missing phase annotation, defaulting to Pending",
            "observed", phase)
        return PhasePending
    }
    return phase
}
```

---

### Concurrency Considerations

**Controller Configuration:**

```go
ctrl.NewControllerManagedBy(mgr).
    WithOptions(controller.Options{
        MaxConcurrentReconciles: 5,  // Limit parallel reconciliations
    }).
    For(&tunnelsv1.CloudflareTunnel{}).
    Complete(r)
```

**ResourceVersion Conflicts:**

- Status updates may fail with conflict errors if resource changed during reconciliation
- Treat 409 Conflict on status update as transient → requeue immediately
- Do NOT retry in-loop; let controller-runtime handle requeue

**Rate Limiting:**

- Default controller-runtime rate limiter is sufficient for most cases
- Consider custom rate limiter if Cloudflare API quota is a concern

**Idempotency:**

- All Visit methods must be idempotent (safe to retry)
- External API calls should use idempotency keys where supported
- State transitions should be deterministic from current state

---

## Stage 1: CloudflareTunnel State Machine

The core tunnel controller - most complex, proves the pattern.

### 1.1 Create State Machine Definition

- [ ] Create `operators/cloudflare/statemachines/` directory
- [ ] Create `operators/cloudflare/statemachines/cloudflaretunnel.sextant.yaml`

**State Machine Design:**

```
Pending → CreatingTunnel → CreatingSecret → ConfiguringIngress → Ready
                ↓              ↓                  ↓                 │
             Failed ←──────────┴──────────────────┘                 │
                ↓                                                   │
             Pending (retry if retryable)                           │
                                                                    │
                         ┌──────────────────────────────────────────┘
                         ↓
ANY STATE + deletionTimestamp → DeletingTunnel → Deleted
```

**States:**
| State | Type | Requeue | Fields |
|-------|------|---------|--------|
| Pending | initial | - | - |
| CreatingTunnel | - | 5s | - |
| CreatingSecret | - | 5s | tunnelID |
| ConfiguringIngress | - | 5s | tunnelID, secretName |
| Ready | terminal | 5m | tunnelID, secretName, active |
| Failed | error | 1m | lastState, errorMessage, retryCount |
| DeletingTunnel | deletion | 5s | tunnelID |
| Deleted | terminal, deletion | - | - |

**Note on Deletion Granularity:** Single `DeletingTunnel` state handles both tunnel and secret cleanup. This is acceptable because:

1. Secret deletion is a local K8s operation (fast, reliable)
2. Tunnel deletion is the slow/fallible external operation
3. If secret deletion fails, the next reconcile will retry (idempotent)

CloudflareAccessPolicy uses two deletion states (`DeletingPolicies` → `DeletingApplication`) because both are external Cloudflare API calls that can fail independently.

### 1.2 Update CRD Types

- [ ] Modify `operators/cloudflare/api/v1/cloudflaretunnel_types.go`
  - [ ] Add `Phase` field to CloudflareTunnelStatus
  - [ ] Add `LastState` field
  - [ ] Add `ErrorMessage` field
  - [ ] Add `RetryCount` field
- [ ] Run `bazel run //operators/cloudflare:generate` to update generated code
- [ ] Run `bazel run //operators/cloudflare:manifests` to update CRD YAML

### 1.3 Generate State Machine Code

- [ ] Run sextant:
  ```bash
  sextant generate statemachines/cloudflaretunnel.sextant.yaml \
    -o internal/statemachine \
    -p statemachine \
    --module github.com/jomcgi/homelab/operators/cloudflare \
    --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
  ```
- [ ] Verify generated files compile:
  - [ ] `cloudflare_tunnel_phases.go`
  - [ ] `cloudflare_tunnel_types.go`
  - [ ] `cloudflare_tunnel_calculator.go`
  - [ ] `cloudflare_tunnel_transitions.go`
  - [ ] `cloudflare_tunnel_visit.go`
  - [ ] `cloudflare_tunnel_observability.go`
  - [ ] `cloudflare_tunnel_status.go`

### 1.4 Rewrite Controller

- [ ] Rewrite `internal/controller/cloudflaretunnel_controller.go`:
  - [ ] Add Calculator field to reconciler struct
  - [ ] Implement `Reconcile()` with calculate → visit pattern
  - [ ] Implement visitor methods:
    - [ ] `VisitPending` - add finalizer, transition to CreatingTunnel
    - [ ] `VisitCreatingTunnel` - call CreateTunnel API
    - [ ] `VisitCreatingSecret` - create K8s secret with tunnel token
    - [ ] `VisitConfiguringIngress` - call UpdateTunnelConfiguration API
    - [ ] `VisitReady` - periodic status check, handle deletion trigger
    - [ ] `VisitFailed` - handle retry or deletion
    - [ ] `VisitDeletingTunnel` - call DeleteTunnel API
    - [ ] `VisitDeleted` - remove finalizer
    - [ ] `VisitUnknown` - reset to Pending

### 1.5 Update Main

- [ ] Modify `cmd/main.go` to initialize Calculator in reconciler

### 1.6 Test

- [ ] Build compiles: `go build ./...`
- [ ] Create test CloudflareTunnel CR
- [ ] Verify state progression: Pending → CreatingTunnel → ... → Ready
- [ ] Verify deletion: Ready → DeletingTunnel → Deleted
- [ ] Verify retry: simulate error → Failed → retry → Pending

---

## Stage 2: CloudflareAccessPolicy State Machine

Similar pattern to CloudflareTunnel but simpler.

### 2.1 Create State Machine Definition

- [ ] Create `operators/cloudflare/statemachines/cloudflareaccesspolicy.sextant.yaml`

**State Machine Design:**

```
Pending → ResolvingTarget → CreatingApplication → CreatingPolicies → Ready
               ↓                   ↓                    ↓               │
            Failed ←───────────────┴────────────────────┘               │
               ↓                                                        │
            Pending (retry if retryable)                                │
                                                                        │
                              ┌─────────────────────────────────────────┘
                              ↓
ANY STATE + deletionTimestamp → DeletingPolicies → DeletingApplication → Deleted
```

**States:**
| State | Type | Requeue | Fields |
|-------|------|---------|--------|
| Pending | initial | - | - |
| ResolvingTarget | - | 5s | - |
| CreatingApplication | - | 5s | targetDomain, accountID |
| CreatingPolicies | - | 5s | targetDomain, accountID, applicationID |
| Ready | terminal | - | targetDomain, accountID, applicationID, policyIDs |
| Failed | error | 1m | lastState, errorMessage, retryCount |
| DeletingPolicies | deletion | - | applicationID, policyIDs |
| DeletingApplication | deletion | - | applicationID |
| Deleted | terminal, deletion | - | - |

### 2.2 Update CRD Types

- [ ] Modify `operators/cloudflare/api/v1/cloudflareaccesspolicy_types.go`
  - [ ] Add `Phase` field to CloudflareAccessPolicyStatus
  - [ ] Add `LastState`, `ErrorMessage`, `RetryCount` fields
  - [ ] Add `AccountID` field (currently missing)
- [ ] Run `bazel run //operators/cloudflare:generate` and `bazel run //operators/cloudflare:manifests`

### 2.3 Generate State Machine Code

- [ ] Run sextant:
  ```bash
  sextant generate statemachines/cloudflareaccesspolicy.sextant.yaml \
    -o internal/statemachine \
    -p statemachine \
    --module github.com/jomcgi/homelab/operators/cloudflare \
    --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
  ```
- [ ] Verify 7 generated files compile

### 2.4 Rewrite Controller

- [ ] Rewrite `internal/controller/cloudflareaccesspolicy_controller.go`:
  - [ ] Implement visitor methods for all states
  - [ ] Wire up Cloudflare Access API calls

### 2.5 Test

- [ ] Build compiles
- [ ] Test state progression with real Access policy

---

## Stage 3: Gateway Controller (Manual State Machine)

Gateway is external Gateway API type - cannot modify its Status. Use annotation-based state tracking.

### 3.1 Define Phase Constants and Helpers

- [ ] Create `internal/controller/gateway_phases.go`:
  - [ ] Phase constants (Pending, CreatingTunnelCRD, WaitingForTunnel, CreatingDeployment, Ready, Failed, Deleting, Deleted)
  - [ ] `getGatewayPhase(gw)` - read from annotation
  - [ ] `setGatewayPhase(gw, phase)` - write to annotation
  - [ ] Phase data storage annotations for tunnelID, accountID, etc.

**State Machine Design:**

```
Pending → ResolvingCredentials → CreatingTunnelCRD → WaitingForTunnel → CreatingDeployment → Ready
                 ↓                     ↓                  ↓                    ↓              │
              Failed ←─────────────────┴──────────────────┴────────────────────┘              │
                 ↓                                                                            │
              Pending (retry if retryable)                                                    │
                                                                                              │
                                        ┌─────────────────────────────────────────────────────┘
                                        ↓
          ANY STATE + deletionTimestamp → Deleting → Deleted (OwnerReferences handle cleanup)
```

### 3.2 Rewrite Controller

- [ ] Rewrite `internal/controller/gateway_controller.go`:
  - [ ] Calculate phase from annotations
  - [ ] Switch on phase (manual exhaustive handling)
  - [ ] Implement phase handlers:
    - [ ] `handlePending` - add finalizer, resolve GatewayClass
    - [ ] `handleResolvingCredentials` - get Cloudflare credentials from secret
    - [ ] `handleCreatingTunnelCRD` - create CloudflareTunnel CR
    - [ ] `handleWaitingForTunnel` - poll CloudflareTunnel status
    - [ ] `handleCreatingDeployment` - create cloudflared Deployment, HPA, PDB
    - [ ] `handleReady` - periodic status sync
    - [ ] `handleFailed` - retry logic
    - [ ] `handleDeleting` - remove finalizer (OwnerRefs handle cleanup)

### 3.3 Test

- [ ] Build compiles
- [ ] Create test Gateway CR
- [ ] Verify CloudflareTunnel CRD gets created
- [ ] Verify cloudflared Deployment gets created
- [ ] Verify deletion cleanup

---

## Stage 4: HTTPRoute Controller (Manual State Machine)

Simplest controller - DNS record management.

### 4.1 Define Phase Constants and Helpers

- [ ] Create `internal/controller/httproute_phases.go`:
  - [ ] Phase constants
  - [ ] Annotation helpers for phase + DNS record IDs

**State Machine Design:**

```
Pending → ResolvingGateway → UpdatingRoutes → CreatingDNS → Ready
               ↓                  ↓               ↓            │
            Failed ←──────────────┴───────────────┘            │
               ↓                                               │
            Pending (retry if retryable)                       │
                                                               │
                            ┌──────────────────────────────────┘
                            ↓
ANY STATE + deletionTimestamp → DeletingDNS → DeletingRoutes → Deleted
```

### 4.2 Rewrite Controller

- [ ] Rewrite `internal/controller/httproute_controller.go`:
  - [ ] Implement phase handlers:
    - [ ] `handleResolvingGateway` - find parent Gateway, get tunnelID
    - [ ] `handleUpdatingRoutes` - update tunnel ingress config
    - [ ] `handleCreatingDNS` - create DNS records for hostnames
    - [ ] `handleReady` - monitor DNS
    - [ ] `handleDeletingDNS` - delete DNS records
    - [ ] `handleDeletingRoutes` - remove routes from tunnel config

### 4.3 Test

- [ ] Build compiles
- [ ] Create test HTTPRoute CR
- [ ] Verify DNS records created
- [ ] Verify deletion cleanup

---

## Stage 5: GatewayClass Controller (Keep Simple)

The GatewayClass controller is a validation-only controller - it validates GatewayClass resources and sets the `Accepted` condition. No state machine needed.

### 5.1 Review and Simplify

- [ ] Review `internal/controller/gatewayclass_controller.go`
- [ ] Verify it only does validation (no complex state)
- [ ] Keep existing implementation - it's appropriately simple
- [ ] Ensure consistent error handling with other controllers

**Current Behavior (keep as-is):**

- Validates GatewayClass `spec.controllerName` matches our controller
- Validates `spec.parametersRef` Secret exists with required fields
- Sets `Accepted` condition True/False based on validation

---

## Stage 6: Service Controller (Keep Simple)

The Service controller watches Services with `cloudflare.ingress.hostname` annotation and manages HTTPRoutes. It's an annotation-driven helper - no state machine needed.

### 6.1 Review and Simplify

- [ ] Review `internal/controller/service_controller.go`
- [ ] Verify it handles annotation-based routing correctly
- [ ] Keep existing implementation - it's appropriately simple
- [ ] Ensure consistent error handling with other controllers

**Current Behavior (keep as-is):**

- Watches Services with `cloudflare.ingress.hostname` annotation
- Creates/updates HTTPRoute resources for annotated Services
- Optionally creates CloudflareAccessPolicy for zero-trust

---

## Stage 7: Integration & Cleanup

### 7.1 Bazel Build Updates

- [ ] Add sextant generation to `operators/cloudflare/BUILD`:
  ```starlark
  # Generate state machine code
  genrule(
      name = "generate-statemachines",
      srcs = [
          "statemachines/cloudflaretunnel.sextant.yaml",
          "statemachines/cloudflareaccesspolicy.sextant.yaml",
      ],
      outs = [
          "internal/statemachine/cloudflare_tunnel_phases.go",
          "internal/statemachine/cloudflare_tunnel_types.go",
          "internal/statemachine/cloudflare_tunnel_calculator.go",
          "internal/statemachine/cloudflare_tunnel_transitions.go",
          "internal/statemachine/cloudflare_tunnel_visit.go",
          "internal/statemachine/cloudflare_tunnel_observability.go",
          "internal/statemachine/cloudflare_tunnel_status.go",
          "internal/statemachine/cloudflare_access_policy_phases.go",
          "internal/statemachine/cloudflare_access_policy_types.go",
          "internal/statemachine/cloudflare_access_policy_calculator.go",
          "internal/statemachine/cloudflare_access_policy_transitions.go",
          "internal/statemachine/cloudflare_access_policy_visit.go",
          "internal/statemachine/cloudflare_access_policy_observability.go",
          "internal/statemachine/cloudflare_access_policy_status.go",
      ],
      cmd = """
          $(location //projects/sextant/cmd/sextant) generate $(location statemachines/cloudflaretunnel.sextant.yaml) \
            -o $(@D)/internal/statemachine \
            -p statemachine \
            --module github.com/jomcgi/homelab/operators/cloudflare \
            --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
          $(location //projects/sextant/cmd/sextant) generate $(location statemachines/cloudflareaccesspolicy.sextant.yaml) \
            -o $(@D)/internal/statemachine \
            -p statemachine \
            --module github.com/jomcgi/homelab/operators/cloudflare \
            --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
      """,
      tools = ["//projects/sextant/cmd/sextant"],
  )
  ```

### 7.2 Full Integration Test

- [ ] Deploy operator to test cluster
- [ ] Create Gateway → verify CloudflareTunnel + Deployment
- [ ] Create HTTPRoute → verify DNS records
- [ ] Create CloudflareAccessPolicy → verify Zero Trust app
- [ ] Delete all → verify cleanup
- [ ] Check SigNoz for OTEL traces showing state transitions

### 7.3 Documentation

- [ ] Update `operators/cloudflare/README.md` with state machine diagrams
- [ ] Document phase field meanings for debugging

---

## File Changes Summary

### Create (new files)

| File                                                | Purpose                                         |
| --------------------------------------------------- | ----------------------------------------------- |
| `statemachines/cloudflaretunnel.sextant.yaml`       | CloudflareTunnel state machine definition       |
| `statemachines/cloudflareaccesspolicy.sextant.yaml` | CloudflareAccessPolicy state machine definition |
| `internal/statemachine/*.go`                        | Generated code (14 files)                       |
| `internal/controller/gateway_phases.go`             | Gateway phase constants + helpers               |
| `internal/controller/httproute_phases.go`           | HTTPRoute phase constants + helpers             |

### Modify (existing files)

| File                                                       | Changes                                |
| ---------------------------------------------------------- | -------------------------------------- |
| `api/v1/cloudflaretunnel_types.go`                         | Add Phase + error tracking fields      |
| `api/v1/cloudflareaccesspolicy_types.go`                   | Add Phase + error tracking fields      |
| `internal/controller/cloudflaretunnel_controller.go`       | Full rewrite with visitor pattern      |
| `internal/controller/cloudflareaccesspolicy_controller.go` | Full rewrite with visitor pattern      |
| `internal/controller/gateway_controller.go`                | Full rewrite with manual state machine |
| `internal/controller/httproute_controller.go`              | Full rewrite with manual state machine |
| `cmd/main.go`                                              | Initialize state machine calculators   |
| `BUILD`                                                    | Add generate-statemachines Bazel rule  |

### Preserve (no changes)

| File                                             | Reason                                       |
| ------------------------------------------------ | -------------------------------------------- |
| `internal/cloudflare/*`                          | API client - reused                          |
| `internal/telemetry/*`                           | OTEL setup - reused                          |
| `internal/controller/gatewayclass_controller.go` | Validation controller - keep simple          |
| `internal/controller/service_controller.go`      | Helper controller - keep simple              |
| `api/v1/conditions.go`                           | Condition constants - kept for compatibility |

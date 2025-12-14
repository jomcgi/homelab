# Cloudflare Operator Rewrite Using Sextant

## Overview

Rewrite the Cloudflare operator's 6 controllers using sextant state machine code generation to replace imperative reconciliation code with declarative state machines.

| Controller | CRD Owner | Phase Storage | Approach |
|------------|-----------|---------------|----------|
| CloudflareTunnel | Us | Status.Phase | Sextant generated |
| CloudflareAccessPolicy | Us | Status.Phase | Sextant generated |
| Gateway | Gateway API (external) | Annotation | Manual state machine |
| HTTPRoute | Gateway API (external) | Annotation | Manual state machine |
| GatewayClass | Gateway API (external) | Status.Conditions | Keep simple (validation only) |
| Service | N/A (helper) | N/A | Keep simple (annotation-based routing) |

**Key Constraint**: Gateway/HTTPRoute/GatewayClass are external Gateway API types - we cannot add `Status.Phase` fields. Use annotation-based phase storage for Gateway/HTTPRoute.

---

## Stage 1: CloudflareTunnel State Machine

The core tunnel controller - most complex, proves the pattern.

### 1.1 Create State Machine Definition

- [ ] Create `operators/cloudflare/statemachines/` directory
- [ ] Create `operators/cloudflare/statemachines/cloudflaretunnel.sextant.yaml`

**State Machine Design:**
```
Pending → CreatingTunnel → CreatingSecret → ConfiguringIngress → Ready
                ↓              ↓                  ↓
             Failed ←──────────┴──────────────────┘
                ↓
             Pending (retry if retryable)

Ready/Failed → DeletingTunnel → Deleted (on deletionTimestamp)
```

**States:**
| State | Type | Requeue | Fields |
|-------|------|---------|--------|
| Pending | initial | - | - |
| CreatingTunnel | - | 5s | - |
| CreatingSecret | - | 5s | tunnelID |
| ConfiguringIngress | - | 5s | tunnelID, secretName |
| Ready | terminal | - | tunnelID, secretName, active |
| Failed | error | 1m | lastState, errorMessage, retryCount |
| DeletingTunnel | deletion | - | tunnelID |
| Deleted | terminal, deletion | - | - |

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
               ↓                   ↓                    ↓
            Failed ←───────────────┴────────────────────┘

Ready/Failed → DeletingPolicies → DeletingApplication → Deleted
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
                 ↓                     ↓                  ↓                    ↓
              Failed ←─────────────────┴──────────────────┴────────────────────┘

Ready/Failed → Deleting → Deleted (OwnerReferences handle cleanup)
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
               ↓                  ↓               ↓
            Failed ←──────────────┴───────────────┘

Ready/Failed → DeletingDNS → DeletingRoutes → Deleted
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
          $(location //sextant/cmd/sextant) generate $(location statemachines/cloudflaretunnel.sextant.yaml) \
            -o $(@D)/internal/statemachine \
            -p statemachine \
            --module github.com/jomcgi/homelab/operators/cloudflare \
            --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
          $(location //sextant/cmd/sextant) generate $(location statemachines/cloudflareaccesspolicy.sextant.yaml) \
            -o $(@D)/internal/statemachine \
            -p statemachine \
            --module github.com/jomcgi/homelab/operators/cloudflare \
            --api github.com/jomcgi/homelab/operators/cloudflare/api/v1
      """,
      tools = ["//sextant/cmd/sextant"],
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
| File | Purpose |
|------|---------|
| `statemachines/cloudflaretunnel.sextant.yaml` | CloudflareTunnel state machine definition |
| `statemachines/cloudflareaccesspolicy.sextant.yaml` | CloudflareAccessPolicy state machine definition |
| `internal/statemachine/*.go` | Generated code (14 files) |
| `internal/controller/gateway_phases.go` | Gateway phase constants + helpers |
| `internal/controller/httproute_phases.go` | HTTPRoute phase constants + helpers |

### Modify (existing files)
| File | Changes |
|------|---------|
| `api/v1/cloudflaretunnel_types.go` | Add Phase + error tracking fields |
| `api/v1/cloudflareaccesspolicy_types.go` | Add Phase + error tracking fields |
| `internal/controller/cloudflaretunnel_controller.go` | Full rewrite with visitor pattern |
| `internal/controller/cloudflareaccesspolicy_controller.go` | Full rewrite with visitor pattern |
| `internal/controller/gateway_controller.go` | Full rewrite with manual state machine |
| `internal/controller/httproute_controller.go` | Full rewrite with manual state machine |
| `cmd/main.go` | Initialize state machine calculators |
| `BUILD` | Add generate-statemachines Bazel rule |

### Preserve (no changes)
| File | Reason |
|------|--------|
| `internal/cloudflare/*` | API client - reused |
| `internal/telemetry/*` | OTEL setup - reused |
| `internal/controller/gatewayclass_controller.go` | Validation controller - keep simple |
| `internal/controller/service_controller.go` | Helper controller - keep simple |
| `api/v1/conditions.go` | Condition constants - kept for compatibility |

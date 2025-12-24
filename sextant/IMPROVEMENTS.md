# Sextant Improvements Plan

## Overview

This document outlines enhancements to sextant required to support production-grade Kubernetes operators. These improvements address gaps identified during the Cloudflare operator rewrite planning.

**Priority**: P1 (blocking operator implementation)

---

## 1. Configurable Error Handling

### Problem Statement

The current implementation has hardcoded retry behavior with no error classification. Production operators need to distinguish between transient errors (retry), permanent errors (fail fast), and conflicts (treat as success for idempotency).

### Requirements

#### 1.1 Schema Changes

- [x] Add `errorHandling` section to `StateMachine` schema in `pkg/schema/types.go`
- [x] Define `ErrorHandlingConfig` struct with:
  - [x] `backoff.base` - Base duration (e.g., "5s")
  - [x] `backoff.multiplier` - Multiplier for exponential backoff (e.g., 2)
  - [x] `backoff.max` - Maximum backoff duration (e.g., "5m")
  - [x] `backoff.jitter` - Jitter percentage (e.g., 0.1 for ±10%)
  - [x] `maxRetries` - Maximum retry count before moving to Failed state
- [x] Add validation for error handling config in `pkg/schema/validate.go`
- [x] Add tests for new schema fields in `pkg/schema/validate_test.go`

#### 1.2 Code Generation Changes

- [x] Update `transitions.go.tmpl` to use configurable backoff:
  ```go
  // Package-level random source, seeded once at init to avoid correlated jitter
  // across operators started simultaneously.
  var jitterRand = rand.New(rand.NewSource(time.Now().UnixNano()))
  var jitterMu sync.Mutex

  func (s {{$.Name}}{{.Name}}) RetryBackoff() time.Duration {
      base := {{.ErrorHandling.Backoff.Base}}
      multiplier := {{.ErrorHandling.Backoff.Multiplier}}
      max := {{.ErrorHandling.Backoff.Max}}
      jitter := {{.ErrorHandling.Backoff.Jitter}}

      backoff := base * time.Duration(math.Pow(float64(multiplier), float64(s.RetryCount)))
      if backoff > max {
          backoff = max
      }
      // Apply jitter with thread-safe random source
      jitterRange := float64(backoff) * jitter
      jitterMu.Lock()
      jitterValue := jitterRand.Float64()*2*jitterRange - jitterRange
      jitterMu.Unlock()
      backoff += time.Duration(jitterValue)
      return backoff
  }
  ```
- [x] Generate `IsMaxRetriesExceeded()` method using configured `maxRetries`
- [x] Update `generator.go` to pass error handling config to templates
- [x] Apply default values when `errorHandling` is not specified

### Acceptance Criteria

- [x] Backoff duration respects configured base, multiplier, max, and jitter
- [x] `IsMaxRetriesExceeded()` returns true when `RetryCount >= maxRetries`
- [x] Existing state machines without `errorHandling` continue to work (defaults applied)
- [x] Generated code compiles and passes tests

---

## 2. Spec Change Detection

### Problem Statement

Operators need to detect when a resource's spec has changed while in a terminal state (e.g., Ready) and trigger re-reconciliation. Currently, the calculator doesn't provide helpers for generation comparison.

### Requirements

#### 2.1 Standalone Helper Function

- [x] Generate `HasSpecChanged()` as standalone function (not Calculator method) in `status.go`:
  ```go
  // HasSpecChanged returns true if spec has changed since last reconciliation.
  // Compares metadata.generation with status.observedGeneration.
  // This is a standalone function to maintain Calculator as a pure state reconstructor.
  func HasSpecChanged(r *{{.Version}}.{{.Name}}) bool {
      return r.Generation != r.Status.ObservedGeneration
  }
  ```

#### 2.2 Schema Changes

- [x] Add `specChangeHandling` section to `StateMachine` schema:
  ```yaml
  specChangeHandling:
    enabled: true
    observedGenerationField: observedGeneration  # Status field name
  ```
- [ ] Add validation to ensure `observedGenerationField` exists in CRD status (requires CRD parsing, deferred)

#### 2.3 Code Generation Changes

- [x] Update `status.go.tmpl` to include standalone `HasSpecChanged()` function
- [x] Generate field accessor for observed generation
- [x] Add helper to update observed generation after successful reconciliation:
  ```go
  // UpdateObservedGeneration returns a copy of the resource with observedGeneration
  // set to the current generation. Call this after successful reconciliation.
  func UpdateObservedGeneration(r *{{.Version}}.{{.Name}}) *{{.Version}}.{{.Name}} {
      r.Status.ObservedGeneration = r.Generation
      return r
  }
  ```

### Acceptance Criteria

- [x] `HasSpecChanged()` correctly compares generations
- [x] Helper method available to update observed generation
- [x] Works with existing state machines (opt-in feature)

---

## 3. Prometheus Metrics Generation

### Problem Statement

Production operators require Prometheus metrics for monitoring. Currently, sextant only generates tracing and logging observers, not metrics.

### Requirements

#### 3.1 Schema Changes

- [x] Extend `Observability` struct in `pkg/schema/types.go`:
  ```go
  type Observability struct {
      OnTransition bool `yaml:"onTransition,omitempty"`
      OTelTracing  bool `yaml:"otelTracing,omitempty"`
      EmbedDiagram bool `yaml:"embedDiagram,omitempty"`
      Metrics      bool `yaml:"metrics,omitempty"`  // NEW
  }
  ```

#### 3.2 New Template

- [x] Create `metrics.go.tmpl` template that generates:
  ```go
  var (
      reconcileTotal = prometheus.NewCounterVec(
          prometheus.CounterOpts{
              Name: "{{lower .Name}}_reconcile_total",
              Help: "Total number of reconciliations",
          },
          []string{"result"},
      )

      reconcileDuration = prometheus.NewHistogramVec(
          prometheus.HistogramOpts{
              Name:    "{{lower .Name}}_reconcile_duration_seconds",
              Help:    "Duration of reconciliations",
              Buckets: prometheus.DefBuckets,
          },
          []string{"phase"},
      )

      resourcePhase = prometheus.NewGaugeVec(
          prometheus.GaugeOpts{
              Name: "{{lower .Name}}_resource_phase",
              Help: "Current phase of resources (1 = in this phase)",
          },
          []string{"namespace", "name", "phase"},
      )

      errorsTotal = prometheus.NewCounterVec(
          prometheus.CounterOpts{
              Name: "{{lower .Name}}_errors_total",
              Help: "Total number of errors by type",
          },
          []string{"error_type"},
      )

      // Time-in-state metric for SLO measurement (e.g., "how long to reach Ready?")
      stateDuration = prometheus.NewHistogramVec(
          prometheus.HistogramOpts{
              Name:    "{{lower .Name}}_state_duration_seconds",
              Help:    "Time spent transitioning between states",
              Buckets: []float64{1, 5, 15, 30, 60, 120, 300, 600, 1800},
          },
          []string{"from_phase", "to_phase"},
      )
  )

  // MetricsObserver implements TransitionObserver with Prometheus metrics.
  type MetricsObserver struct {
      transitionStart map[string]time.Time  // key: namespace/name
      mu              sync.Mutex
  }

  func NewMetricsObserver() *MetricsObserver {
      return &MetricsObserver{
          transitionStart: make(map[string]time.Time),
      }
  }

  func (m *MetricsObserver) OnTransition(ctx context.Context, from, to {{.Name}}State) {
      key := to.Resource().Namespace + "/" + to.Resource().Name

      m.mu.Lock()
      if startTime, ok := m.transitionStart[key]; ok {
          // Record duration from previous state
          stateDuration.WithLabelValues(from.Phase(), to.Phase()).
              Observe(time.Since(startTime).Seconds())
      }
      m.transitionStart[key] = time.Now()
      m.mu.Unlock()

      resourcePhase.WithLabelValues(
          to.Resource().Namespace,
          to.Resource().Name,
          to.Phase(),
      ).Set(1)
      // Reset previous phase
      resourcePhase.WithLabelValues(
          from.Resource().Namespace,
          from.Resource().Name,
          from.Phase(),
      ).Set(0)
  }

  func init() {
      prometheus.MustRegister(reconcileTotal, reconcileDuration, resourcePhase, errorsTotal, stateDuration)
  }
  ```

#### 3.3 Generator Updates

- [x] Update `generator.go` to generate `metrics.go` when `observability.metrics: true`
- [x] Add prometheus dependency to generated imports

### Acceptance Criteria

- [x] Metrics file generated when `observability.metrics: true`
- [x] All five metrics generated:
  - [x] `reconcile_total` (counter)
  - [x] `reconcile_duration_seconds` (histogram)
  - [x] `resource_phase` (gauge)
  - [x] `errors_total` (counter)
  - [x] `state_duration_seconds` (histogram) - for SLO measurement
- [x] Metrics registered on init
- [x] MetricsObserver implements TransitionObserver interface
- [x] MetricsObserver tracks transition timestamps for duration calculation
- [x] Metrics have appropriate labels and help text

---

## 4. Enhanced Guard Conditions

### Problem Statement

Guards currently only support `maxRetries`. Production operators need more expressive guard conditions for complex retry logic.

### Requirements

#### 4.1 Schema Changes

- [x] Extend `Guard` struct to support additional conditions:
  ```go
  type Guard struct {
      Description   string        `yaml:"description,omitempty"`
      MaxRetries    int           `yaml:"maxRetries,omitempty"`
      MinBackoff    Duration      `yaml:"minBackoff,omitempty"`    // NEW: Enforces a minimum time before retry (max of this vs ErrorHandling)
      Condition     string        `yaml:"condition,omitempty"`     // NEW: Go expression using 's' (state) and 'r' (resource)
  }
  ```

#### 4.2 Code Generation

- [x] Generate guard evaluation that combines multiple conditions
- [x] Support user-defined condition expressions (validated at generation time)
  - [x] Context available: `s` (current state struct), `r` (resource struct)
  - [x] Example: `r.Spec.Replicas > 0`
  - [x] Safety: Condition expressions embedded directly; invalid expressions fail at compile time

### Acceptance Criteria

- [x] Guards can specify multiple conditions
- [x] Generated code correctly evaluates combined conditions
- [x] Invalid conditions fail at generation time, not runtime (fail at compile time)

---

## 5. Documentation Generation

### Current State

Mermaid diagram generation **already exists** via `embedDiagram: true` in `types.go.tmpl:14-27`. However, there's a bug with multi-source transitions.

### Problem Statement

The current diagram generation uses `{{index .From 0}}` which only shows the first source state for transitions with multiple sources. A transition like `from: ["Ready", "Failed"]` only renders `Ready --> To`, missing `Failed --> To`.

### Requirements

#### 5.1 Fix Multi-Source Transition Bug

- [x] Update `types.go.tmpl` to iterate over all source states:
  ```go
  {{- range .Transitions}}
  {{- range .From}}
  //     {{.}} --> {{$.To}}: {{$.Action}}{{if $.Guard}} [{{$.Guard}}]{{end}}
  {{- end}}
  {{- end}}
  ```

#### 5.2 Optional Standalone Documentation (P3)

- [ ] Add state transition table to generated code comments
- [ ] Generate markdown documentation file (optional):
  ```yaml
  observability:
    generateDocs: true  # Generates STATE_MACHINE.md
  ```

### Acceptance Criteria

- [x] Mermaid diagram shows ALL edges for multi-source transitions
- [ ] Generated markdown includes state descriptions, transitions, and guards (P3 - deferred)
- [ ] Documentation stays in sync with YAML definition (P3 - deferred)

---

## Implementation Order

1. **Error Handling** (P1) - Blocks operator implementation
2. **Spec Change Detection** (P1) - Required for Ready state handling
3. **Prometheus Metrics** (P2) - Required for production monitoring
4. **Enhanced Guards** (P3) - Nice to have
5. **Documentation** (P3) - Nice to have

---

## Testing Strategy

### Unit Tests
- [x] Schema validation tests for new fields
- [x] Template rendering tests for generated code
- [x] Backoff calculation tests with edge cases

### Integration Tests
- [x] Generate code from test YAML, compile, and verify behavior
- [ ] Test metrics registration and emission (requires runtime test)
- [ ] Test spec change detection with mock resources (requires runtime test)

### Example Updates
- [ ] Update `examples/` with new features demonstrated
- [ ] Ensure examples compile and serve as documentation

---

## Migration Path

Existing state machine definitions must continue to work:

1. All new schema fields are optional
2. Sensible defaults applied when fields are omitted
3. No breaking changes to generated code signatures
4. Deprecation warnings for any changed behavior

---

## Design Decisions

1. **Metrics namespace**: Per-controller. Each controller gets its own metric names (e.g., `cloudflaretunnel_reconcile_total`, `cloudflareaccesspolicy_reconcile_total`). This allows independent scaling and monitoring.

2. **Alert generation**: Leave to Helm charts. Sextant generates metrics only. PrometheusRule CRDs are deployment-specific and belong in the operator's Helm chart values.

3. **Spec change detection**: Opt-in via schema. Explicit is better than implicit. Controllers that need it enable `specChangeHandling.enabled: true`.

---

## References

- [Cloudflare Operator Rewrite Plan](../operators/cloudflare/SEXTANT_REWRITE_PLAN.md)
- [Kubernetes Controller Best Practices](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-api-machinery/controllers.md)
- [Prometheus Go Client](https://github.com/prometheus/client_golang)

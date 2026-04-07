package statemachine

// Tests targeting the coverage gaps identified in the research report:
//
// 1. calculateDeletionState with non-zero DeletionTimestamp (gaps #2)
// 2. PhaseUnknown + empty ObservedPhase validation fallback (gap #3)
// 3. ModelCacheFuncVisitor Default callback and nil-handler zero-value returns (gap #4)
// 4. IsRetryable() with Permanent: true (gap #5)

import (
	"testing"
	"time"

	"github.com/go-logr/logr/testr"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// =============================================================================
// Gap #2 – calculateDeletionState with non-zero DeletionTimestamp
// =============================================================================

// calculateDeletionState delegates to calculateNormalState, so the
// DeletionTimestamp path must produce the same concrete type as the
// normal path for a given phase.
func TestCalculator_DeletionTimestamp_PendingPhase_ReturnsPending(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: PhasePending,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCachePending); !ok {
		t.Errorf("expected ModelCachePending for deleted resource in Pending phase, got %T", state)
	}
}

func TestCalculator_DeletionTimestamp_ReadyPhase_ReturnsReady(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseReady,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			Digest:           "sha256:abc123",
			ResolvedRevision: "main",
			Format:           "safetensors",
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheReady); !ok {
		t.Errorf("expected ModelCacheReady for deleted resource in Ready phase, got %T", state)
	}
}

func TestCalculator_DeletionTimestamp_ResolvingPhase_ValidStatus_ReturnsResolving(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseResolving,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "main",
			Format:           "gguf",
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheResolving); !ok {
		t.Errorf("expected ModelCacheResolving for deleted resource in Resolving phase, got %T", state)
	}
}

// Ensures that pod ungating still works when a resource is deleted mid-sync:
// calculateDeletionState falls through to calculateNormalState which validates
// status, and a corrupt SyncJob falls back to Unknown so the reconciler can
// still process the deletion gracefully.
func TestCalculator_DeletionTimestamp_SyncingPhase_InvalidStatus_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseSyncing,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "main",
			Format:           "safetensors",
			// SyncJobName intentionally empty → validation fails
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheUnknown); !ok {
		t.Errorf("expected ModelCacheUnknown when deleted resource has invalid status, got %T", state)
	}
}

// =============================================================================
// Gap #3 – PhaseUnknown + empty ObservedPhase → validation-fail-within-Unknown
// =============================================================================

// When the stored phase is "Unknown" but ObservedPhase is missing, Validate()
// fails and the calculator must fall back to a fresh ModelCacheUnknown whose
// ObservedPhase is "Unknown" (the stored phase string).
func TestCalculator_PhaseUnknown_EmptyObservedPhase_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-model",
			Namespace: "default",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:         PhaseUnknown,
			ObservedPhase: "", // intentionally missing → Validate() returns error
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Errorf("expected ModelCacheUnknown for PhaseUnknown with empty ObservedPhase, got %T", state)
	}
	// The fallback Unknown state uses the stored phase ("Unknown") as its ObservedPhase.
	if unknown.ObservedPhase != PhaseUnknown {
		t.Errorf("expected ObservedPhase=%q, got %q", PhaseUnknown, unknown.ObservedPhase)
	}
}

// When PhaseUnknown has a valid ObservedPhase, the state is returned directly.
func TestCalculator_PhaseUnknown_ValidObservedPhase_ReturnsUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-model",
			Namespace: "default",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:         PhaseUnknown,
			ObservedPhase: "Syncing", // was in Syncing before going Unknown
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Errorf("expected ModelCacheUnknown, got %T", state)
	}
	if unknown.ObservedPhase != "Syncing" {
		t.Errorf("expected ObservedPhase=%q, got %q", "Syncing", unknown.ObservedPhase)
	}
}

// =============================================================================
// Gap #4 – ModelCacheFuncVisitor Default callback and nil-handler zero-value
// =============================================================================

// When a specific On* handler is nil and Default is set, Default should be
// called instead for every state that lacks a specific handler.
func TestFuncVisitor_Default_CalledWhenHandlerNil(t *testing.T) {
	mc := newMC("")
	defaultCalled := 0
	visitor := &ModelCacheFuncVisitor[string]{
		// Intentionally leave all On* handlers nil
		Default: func(_ ModelCacheState) string {
			defaultCalled++
			return "default"
		},
	}

	states := []ModelCacheState{
		ModelCachePending{resource: mc},
		ModelCacheResolving{resource: mc},
		ModelCacheSyncing{resource: mc},
		ModelCacheReady{resource: mc},
		ModelCacheFailed{resource: mc},
		ModelCacheUnknown{resource: mc, ObservedPhase: "x"},
	}

	for _, s := range states {
		got := Visit(s, visitor)
		if got != "default" {
			t.Errorf("Visit(%T) = %q; want %q", s, got, "default")
		}
	}
	if defaultCalled != len(states) {
		t.Errorf("Default called %d times; want %d", defaultCalled, len(states))
	}
}

// When a specific On* handler fires, Default must NOT be called.
func TestFuncVisitor_SpecificHandlerTakesPrecedenceOverDefault(t *testing.T) {
	mc := newMC("")
	defaultCalled := false
	visitor := &ModelCacheFuncVisitor[string]{
		OnPending: func(_ ModelCachePending) string { return "specific" },
		Default: func(_ ModelCacheState) string {
			defaultCalled = true
			return "default"
		},
	}

	got := Visit(ModelCachePending{resource: mc}, visitor)
	if got != "specific" {
		t.Errorf("expected %q, got %q", "specific", got)
	}
	if defaultCalled {
		t.Error("Default should not be called when specific handler is set")
	}
}

// When both the specific On* handler AND Default are nil, Visit must return
// the zero value of T without panicking.
func TestFuncVisitor_NilHandler_NilDefault_ReturnsZeroValue(t *testing.T) {
	mc := newMC("")
	visitor := &ModelCacheFuncVisitor[string]{
		// all fields nil
	}

	states := []ModelCacheState{
		ModelCachePending{resource: mc},
		ModelCacheResolving{resource: mc},
		ModelCacheSyncing{resource: mc},
		ModelCacheReady{resource: mc},
		ModelCacheFailed{resource: mc},
		ModelCacheUnknown{resource: mc, ObservedPhase: "x"},
	}

	for _, s := range states {
		got := Visit(s, visitor)
		if got != "" {
			t.Errorf("Visit(%T) with nil handlers = %q; want zero value (empty string)", s, got)
		}
	}
}

// Integer zero value variant — ensures the zero-value return isn't accidentally
// string-specific.
func TestFuncVisitor_NilHandler_NilDefault_ReturnsZeroInt(t *testing.T) {
	mc := newMC("")
	visitor := &ModelCacheFuncVisitor[int]{}

	got := Visit[int](ModelCachePending{resource: mc}, visitor)
	if got != 0 {
		t.Errorf("Visit with nil int visitor = %d; want 0", got)
	}
}

// Boolean zero value.
func TestFuncVisitor_NilHandler_NilDefault_ReturnsZeroBool(t *testing.T) {
	mc := newMC("")
	visitor := &ModelCacheFuncVisitor[bool]{}

	got := Visit[bool](ModelCacheUnknown{resource: mc, ObservedPhase: "x"}, visitor)
	if got {
		t.Error("Visit with nil bool visitor should return false")
	}
}

// =============================================================================
// Gap #5 – IsRetryable() with Permanent: true
// =============================================================================

// IsRetryable() always returns true for ModelCacheFailed regardless of the
// Permanent flag. The Permanent guard is enforced by the Retry() method
// (which returns nil when Permanent=true), NOT by IsRetryable().
//
// This test documents that surprising invariant so it cannot silently change.
func TestFailed_IsRetryable_AlwaysTrueEvenWhenPermanent(t *testing.T) {
	mc := newMC(PhaseFailed)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: true, LastState: "Pending", ErrorMessage: "permanent error"},
	}

	if !failed.IsRetryable() {
		t.Error("IsRetryable() should return true even when Permanent=true; " +
			"the guard lives in Retry(), not IsRetryable()")
	}
}

// Cross-check: Retry() returns nil when Permanent=true, confirming that
// IsRetryable()=true does NOT mean the Retry transition will succeed.
func TestFailed_IsRetryable_TrueButRetry_NilWhenPermanent(t *testing.T) {
	mc := newMC(PhaseFailed)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: true, LastState: "Pending", ErrorMessage: "bad format"},
	}

	if !failed.IsRetryable() {
		t.Fatal("precondition: IsRetryable() must be true")
	}
	if next := failed.Retry(); next != nil {
		t.Errorf("Retry() should return nil when Permanent=true, got %+v", next)
	}
}

// Symmetry: when Permanent=false, both IsRetryable and Retry succeed.
func TestFailed_IsRetryable_TrueAndRetry_NonNilWhenTransient(t *testing.T) {
	mc := newMC(PhaseFailed)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: false, LastState: "Pending", ErrorMessage: "network timeout"},
	}

	if !failed.IsRetryable() {
		t.Fatal("IsRetryable() must be true for transient errors")
	}
	if next := failed.Retry(); next == nil {
		t.Error("Retry() must return non-nil for transient errors")
	}
}

// Ensure the time import is used (compile-time check).
var _ = time.Now

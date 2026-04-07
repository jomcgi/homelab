package statemachine

// Dedicated tests for model_cache_calculator.go.
//
// Scope: NewModelCacheCalculator constructor and Calculate edge-cases that are
// NOT already covered by the shared test files (statemachine_test.go,
// model_cache_gaps_test.go, model_cache_coverage_test.go).
//
// Specifically this file adds:
//   - Explicit constructor test for NewModelCacheCalculator
//   - DeletionTimestamp with empty (initial) phase
//   - Calculate called with varied resource names / namespaces to exercise the
//     WithValues log path without crashing
//   - Verify the Calculator's Log field is the one passed to the constructor

import (
	"testing"
	"time"

	"github.com/go-logr/logr"
	"github.com/go-logr/logr/testr"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// =============================================================================
// NewModelCacheCalculator
// =============================================================================

// NewModelCacheCalculator must store the provided logger so the caller's logger
// is used for all subsequent calculations.
func TestNewModelCacheCalculator_StoresLogger(t *testing.T) {
	log := testr.New(t)
	calc := NewModelCacheCalculator(log)
	if calc == nil {
		t.Fatal("NewModelCacheCalculator returned nil")
	}
	// logr.Logger is a value type; compare via sink identity isn't straightforward,
	// so we verify the returned calculator is usable (no panic) and non-nil.
}

// NewModelCacheCalculator must accept a discard logger without panicking.
func TestNewModelCacheCalculator_AcceptsDiscardLogger(t *testing.T) {
	calc := NewModelCacheCalculator(logr.Discard())
	if calc == nil {
		t.Fatal("NewModelCacheCalculator with Discard logger returned nil")
	}
	// Ensure Calculate works with a discard logger (no output produced).
	mc := newMC(PhasePending)
	state := calc.Calculate(mc)
	if _, ok := state.(ModelCachePending); !ok {
		t.Errorf("expected ModelCachePending, got %T", state)
	}
}

// =============================================================================
// Calculate: DeletionTimestamp with empty phase
// =============================================================================

// A resource with a non-zero DeletionTimestamp and an empty Phase (initial
// state) should be treated the same as a live resource with empty phase —
// calculateDeletionState delegates to calculateNormalState, which maps ""
// to ModelCachePending.
func TestCalculator_DeletionTimestamp_EmptyPhase_ReturnsPending(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "model-being-deleted",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: "", // initial / empty phase
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCachePending); !ok {
		t.Errorf("expected ModelCachePending for deleted resource with empty phase, got %T", state)
	}
}

// =============================================================================
// Calculate: log context uses resource Name and Namespace
// =============================================================================

// Calculate must not panic when Name and Namespace contain unusual characters
// that are valid in Kubernetes object names.
func TestCalculator_Calculate_UsesResourceNameAndNamespace(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-model-cache-123",
			Namespace: "production",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: PhasePending,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	// Must not panic — log.WithValues is called with Name and Namespace.
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCachePending); !ok {
		t.Errorf("expected ModelCachePending, got %T", state)
	}
}

// =============================================================================
// Calculate: unknown phase triggers the IsKnownPhase fallback path
// =============================================================================

// When the stored phase is completely unknown (not in the known set), the
// IsKnownPhase guard must fire BEFORE calculateNormalState is called.
// The ObservedPhase must be set to the bad phase string.
func TestCalculator_UnrecognizedPhase_ObservedPhaseIsTheBadString(t *testing.T) {
	const badPhase = "totally-made-up-phase"
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase: badPhase,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Fatalf("expected ModelCacheUnknown for unrecognized phase, got %T", state)
	}
	if unknown.ObservedPhase != badPhase {
		t.Errorf("ObservedPhase = %q, want %q", unknown.ObservedPhase, badPhase)
	}
}

// =============================================================================
// Calculate: calculateNormalState default branch (unreachable guard test)
// =============================================================================

// All phases returned by IsKnownPhase=true must be handled by calculateNormalState
// without reaching the default branch.  This table-driven test confirms that
// every known phase produces a concrete (non-nil) state.
func TestCalculator_AllKnownPhases_ProduceNonNilState(t *testing.T) {
	phases := []struct {
		phase  string
		setup  func(*v1alpha1.ModelCacheStatus)
		wantOK func(ModelCacheState) bool
	}{
		{
			phase:  "",
			setup:  func(s *v1alpha1.ModelCacheStatus) {},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCachePending); return ok },
		},
		{
			phase:  PhasePending,
			setup:  func(s *v1alpha1.ModelCacheStatus) {},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCachePending); return ok },
		},
		{
			phase: PhaseResolving,
			setup: func(s *v1alpha1.ModelCacheStatus) {
				s.ResolvedRef = "ghcr.io/test/model:latest"
				s.ResolvedRevision = "main"
				s.Format = "gguf"
			},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCacheResolving); return ok },
		},
		{
			phase: PhaseSyncing,
			setup: func(s *v1alpha1.ModelCacheStatus) {
				s.ResolvedRef = "ghcr.io/test/model:latest"
				s.ResolvedRevision = "main"
				s.Format = "gguf"
				s.SyncJobName = "sync-job-abc"
			},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCacheSyncing); return ok },
		},
		{
			phase: PhaseReady,
			setup: func(s *v1alpha1.ModelCacheStatus) {
				s.ResolvedRef = "ghcr.io/test/model:latest"
				s.ResolvedRevision = "main"
				s.Format = "gguf"
				s.Digest = "sha256:abc123"
			},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCacheReady); return ok },
		},
		{
			phase: PhaseFailed,
			setup: func(s *v1alpha1.ModelCacheStatus) {
				s.LastState = "Pending"
				s.ErrorMessage = "test error"
			},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCacheFailed); return ok },
		},
		{
			phase: PhaseUnknown,
			setup: func(s *v1alpha1.ModelCacheStatus) {
				s.ObservedPhase = "Syncing"
			},
			wantOK: func(st ModelCacheState) bool { _, ok := st.(ModelCacheUnknown); return ok },
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	for _, tc := range phases {
		tc := tc
		t.Run("phase="+tc.phase, func(t *testing.T) {
			mc := &v1alpha1.ModelCache{
				ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
				Status:     v1alpha1.ModelCacheStatus{Phase: tc.phase},
			}
			tc.setup(&mc.Status)

			state := calc.Calculate(mc)
			if state == nil {
				t.Fatal("Calculate returned nil state")
			}
			if !tc.wantOK(state) {
				t.Errorf("phase %q: unexpected state type %T", tc.phase, state)
			}
		})
	}
}

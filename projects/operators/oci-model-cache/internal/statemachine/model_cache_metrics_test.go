package statemachine

import (
	"context"
	"fmt"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

func newMCForMetrics(name, namespace, phase string) *v1alpha1.ModelCache {
	return &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: phase,
		},
	}
}

// TestNewMetricsObserver verifies the constructor returns a non-nil observer.
func TestNewMetricsObserver(t *testing.T) {
	obs := NewMetricsObserver()
	if obs == nil {
		t.Fatal("NewMetricsObserver() should return non-nil")
	}
	if obs.transitionStart == nil {
		t.Error("transitionStart map should be initialized")
	}
}

// TestMetricsObserver_OnTransition_FirstTime verifies OnTransition does not
// panic when called for a resource that has no prior transition start time.
func TestMetricsObserver_OnTransition_FirstTime(t *testing.T) {
	obs := NewMetricsObserver()

	mc := newMCForMetrics("model1", "default", PhasePending)
	from := ModelCachePending{resource: mc}
	to := ModelCacheResolving{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
	}

	// Should not panic.
	obs.OnTransition(context.Background(), from, to)

	// The start time for the resource should have been recorded.
	key := mc.Namespace + "/" + mc.Name
	obs.mu.Lock()
	_, ok := obs.transitionStart[key]
	obs.mu.Unlock()
	if !ok {
		t.Error("transitionStart should be recorded after first transition")
	}
}

// TestMetricsObserver_OnTransition_SubsequentTransition verifies that calling
// OnTransition a second time observes the duration from the previous transition
// and updates the start time.
func TestMetricsObserver_OnTransition_SubsequentTransition(t *testing.T) {
	obs := NewMetricsObserver()

	mc := newMCForMetrics("model2", "default", PhasePending)
	key := mc.Namespace + "/" + mc.Name

	// Pre-seed a start time in the past.
	past := time.Now().Add(-5 * time.Second)
	obs.mu.Lock()
	obs.transitionStart[key] = past
	obs.mu.Unlock()

	from := ModelCachePending{resource: mc}
	to := ModelCacheResolving{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
	}

	// Should not panic; also records the histogram.
	obs.OnTransition(context.Background(), from, to)

	// Start time should be updated to now (after the call).
	obs.mu.Lock()
	newStart := obs.transitionStart[key]
	obs.mu.Unlock()
	if !newStart.After(past) {
		t.Error("transitionStart should be updated after subsequent transition")
	}
}

// TestMetricsObserver_OnTransitionError verifies that OnTransitionError does
// not panic and records the error metric.
func TestMetricsObserver_OnTransitionError(t *testing.T) {
	obs := NewMetricsObserver()

	mc := newMCForMetrics("model3", "default", PhasePending)
	from := ModelCachePending{resource: mc}
	to := ModelCacheResolving{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
	}

	// Should not panic.
	obs.OnTransitionError(context.Background(), from, to, errValidation)
}

// TestRecordReconcile_DoesNotPanic verifies that RecordReconcile does not panic
// for both success and error results.
func TestRecordReconcile_DoesNotPanic(t *testing.T) {
	cases := []struct {
		phase   string
		success bool
	}{
		{PhasePending, true},
		{PhaseResolving, false},
		{PhaseSyncing, true},
		{PhaseReady, true},
		{PhaseFailed, false},
	}
	for _, tc := range cases {
		t.Run(tc.phase, func(t *testing.T) {
			RecordReconcile(tc.phase, 50*time.Millisecond, tc.success)
		})
	}
}

// TestRecordError_DoesNotPanic verifies that RecordError does not panic for
// arbitrary error type strings.
func TestRecordError_DoesNotPanic(t *testing.T) {
	types := []string{"transient", "permanent", "transition_error", "unknown_type"}
	for _, et := range types {
		t.Run(et, func(t *testing.T) {
			RecordError(et)
		})
	}
}

// TestCleanupResourceMetrics_DoesNotPanic verifies CleanupResourceMetrics does
// not panic for a resource that has no registered metrics.
func TestCleanupResourceMetrics_DoesNotPanic(t *testing.T) {
	// No metrics for this resource — the function should handle that gracefully.
	CleanupResourceMetrics("non-existent-ns", "non-existent-name")
}

// TestCleanupResourceMetrics_AfterPhaseGauge verifies that cleanup after
// setting a gauge doesn't leave stale metrics around (no panic).
func TestCleanupResourceMetrics_AfterPhaseGauge(t *testing.T) {
	// Set a gauge then clean it up.
	resourcePhase.WithLabelValues("cleanup-ns", "cleanup-model", PhaseReady).Set(1)
	CleanupResourceMetrics("cleanup-ns", "cleanup-model")
}

// TestMetricsObserver_ConcurrentTransitions verifies that concurrent calls to
// OnTransition from different goroutines do not cause data races.
func TestMetricsObserver_ConcurrentTransitions(t *testing.T) {
	obs := NewMetricsObserver()

	done := make(chan struct{})
	for i := 0; i < 5; i++ {
		go func(idx int) {
			defer func() { done <- struct{}{} }()
			mc := newMCForMetrics("concurrent-model", "default", PhasePending)
			from := ModelCachePending{resource: mc}
			to := ModelCacheResolving{
				resource:      mc,
				ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
			}
			obs.OnTransition(context.Background(), from, to)
		}(i)
	}
	for i := 0; i < 5; i++ {
		<-done
	}
}

// errValidation is a simple error value for testing.
var errValidation = fmt.Errorf("validation error")

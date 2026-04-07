package statemachine

// Tests for coverage gaps across calculator, transitions, phases, and visit files.
// These complement the existing test suite and target specific uncovered branches:
//
// 1. Calculator: DeletionTimestamp + Syncing (valid), Failed (valid/invalid), Unknown phases
// 2. Calculator: field mapping verification (TotalSize, FileCount, Digest, Permanent)
// 3. Transitions: all-field propagation through Resolved, CacheHit, JobCreated, SyncComplete
// 4. Transitions: resource pointer propagation through every transition method
// 5. Visit: FuncVisitor specific handler precedence for all 6 states (not just Pending)
// 6. Visit: Default handler receives the state argument
// 7. Phases: AllPhases order is deterministic; IsKnownPhase rejects near-miss strings

import (
	"testing"
	"time"

	"github.com/go-logr/logr/testr"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// =============================================================================
// Calculator: DeletionTimestamp for Syncing (valid), Failed (valid/invalid), Unknown
// =============================================================================

// Valid Syncing with DeletionTimestamp should return ModelCacheSyncing, not Unknown.
// This covers the path where calculateDeletionState → calculateNormalState returns
// a valid Syncing state so the reconciler can finish ungating pods before GC.
func TestCalculator_DeletionTimestamp_SyncingPhase_ValidStatus_ReturnsSyncing(t *testing.T) {
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
			SyncJobName:      "sync-job-abc",
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	syncing, ok := state.(ModelCacheSyncing)
	if !ok {
		t.Errorf("expected ModelCacheSyncing for deleted resource in valid Syncing phase, got %T", state)
	}
	if syncing.SyncJobName != "sync-job-abc" {
		t.Errorf("SyncJobName not propagated: got %q", syncing.SyncJobName)
	}
}

// Valid Failed phase with DeletionTimestamp should return ModelCacheFailed.
// Ensures the reconciler can act on the failure state before the resource is GC'd.
func TestCalculator_DeletionTimestamp_FailedPhase_ValidStatus_ReturnsFailed(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:        PhaseFailed,
			ErrorMessage: "network timeout",
			LastState:    "Resolving",
			Permanent:    false,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	failed, ok := state.(ModelCacheFailed)
	if !ok {
		t.Errorf("expected ModelCacheFailed for deleted resource in Failed phase, got %T", state)
	}
	if failed.ErrorMessage != "network timeout" {
		t.Errorf("ErrorMessage mismatch: got %q", failed.ErrorMessage)
	}
}

// Invalid Failed phase (missing ErrorMessage) with DeletionTimestamp falls back to Unknown.
func TestCalculator_DeletionTimestamp_FailedPhase_InvalidStatus_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:     PhaseFailed,
			LastState: "Resolving",
			// ErrorMessage intentionally empty → Validate() fails
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheUnknown); !ok {
		t.Errorf("expected ModelCacheUnknown for deleted resource with invalid Failed status, got %T", state)
	}
}

// Unknown phase with DeletionTimestamp and valid ObservedPhase should return ModelCacheUnknown.
func TestCalculator_DeletionTimestamp_UnknownPhase_ValidObservedPhase_ReturnsUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "test-model",
			Namespace:         "default",
			DeletionTimestamp: &metav1.Time{Time: time.Now()},
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:         PhaseUnknown,
			ObservedPhase: "Syncing",
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Errorf("expected ModelCacheUnknown for deleted resource in Unknown phase, got %T", state)
	}
	if unknown.ObservedPhase != "Syncing" {
		t.Errorf("ObservedPhase not propagated: got %q, want %q", unknown.ObservedPhase, "Syncing")
	}
}

// =============================================================================
// Calculator: field mapping — verifies all status fields are copied into states
// =============================================================================

// Resolving state must map ALL fields from Status including optional ones.
func TestCalculator_ResolvingPhase_MapsAllStatusFields(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseResolving,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "rev-abc123",
			Format:           "gguf",
			Digest:           "sha256:interim",
			FileCount:        7,
			TotalSize:        1234567890,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	resolving, ok := state.(ModelCacheResolving)
	if !ok {
		t.Fatalf("expected ModelCacheResolving, got %T", state)
	}
	if resolving.ResolvedRef != mc.Status.ResolvedRef {
		t.Errorf("ResolvedRef: got %q, want %q", resolving.ResolvedRef, mc.Status.ResolvedRef)
	}
	if resolving.ResolvedRevision != mc.Status.ResolvedRevision {
		t.Errorf("ResolvedRevision: got %q, want %q", resolving.ResolvedRevision, mc.Status.ResolvedRevision)
	}
	if resolving.Format != mc.Status.Format {
		t.Errorf("Format: got %q, want %q", resolving.Format, mc.Status.Format)
	}
	if resolving.Digest != mc.Status.Digest {
		t.Errorf("Digest: got %q, want %q", resolving.Digest, mc.Status.Digest)
	}
	if resolving.FileCount != mc.Status.FileCount {
		t.Errorf("FileCount: got %d, want %d", resolving.FileCount, mc.Status.FileCount)
	}
	if resolving.TotalSize != mc.Status.TotalSize {
		t.Errorf("TotalSize: got %d, want %d", resolving.TotalSize, mc.Status.TotalSize)
	}
}

// Syncing state must map ALL fields including SyncJobName, FileCount, and TotalSize.
func TestCalculator_SyncingPhase_MapsAllStatusFields(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseSyncing,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "rev-abc123",
			Format:           "safetensors",
			Digest:           "sha256:in-progress",
			SyncJobName:      "sync-job-xyz",
			FileCount:        14,
			TotalSize:        9876543210,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	syncing, ok := state.(ModelCacheSyncing)
	if !ok {
		t.Fatalf("expected ModelCacheSyncing, got %T", state)
	}
	if syncing.SyncJobName != mc.Status.SyncJobName {
		t.Errorf("SyncJobName: got %q, want %q", syncing.SyncJobName, mc.Status.SyncJobName)
	}
	if syncing.FileCount != mc.Status.FileCount {
		t.Errorf("FileCount: got %d, want %d", syncing.FileCount, mc.Status.FileCount)
	}
	if syncing.TotalSize != mc.Status.TotalSize {
		t.Errorf("TotalSize: got %d, want %d", syncing.TotalSize, mc.Status.TotalSize)
	}
	if syncing.Digest != mc.Status.Digest {
		t.Errorf("Digest: got %q, want %q", syncing.Digest, mc.Status.Digest)
	}
	if syncing.ResolvedRef != mc.Status.ResolvedRef {
		t.Errorf("ResolvedRef: got %q, want %q", syncing.ResolvedRef, mc.Status.ResolvedRef)
	}
}

// Ready state must map Digest, FileCount, and TotalSize correctly.
func TestCalculator_ReadyPhase_MapsAllStatusFields(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase:            PhaseReady,
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "rev-abc123",
			Format:           "safetensors",
			Digest:           "sha256:final-digest",
			FileCount:        21,
			TotalSize:        5000000000,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	ready, ok := state.(ModelCacheReady)
	if !ok {
		t.Fatalf("expected ModelCacheReady, got %T", state)
	}
	if ready.Digest != mc.Status.Digest {
		t.Errorf("Digest: got %q, want %q", ready.Digest, mc.Status.Digest)
	}
	if ready.FileCount != mc.Status.FileCount {
		t.Errorf("FileCount: got %d, want %d", ready.FileCount, mc.Status.FileCount)
	}
	if ready.TotalSize != mc.Status.TotalSize {
		t.Errorf("TotalSize: got %d, want %d", ready.TotalSize, mc.Status.TotalSize)
	}
	if ready.ResolvedRef != mc.Status.ResolvedRef {
		t.Errorf("ResolvedRef: got %q, want %q", ready.ResolvedRef, mc.Status.ResolvedRef)
	}
}

// Failed state must map ALL error fields including the Permanent bool.
func TestCalculator_FailedPhase_MapsAllStatusFields(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase:        PhaseFailed,
			ErrorMessage: "model format not supported",
			LastState:    "Resolving",
			Permanent:    true,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	failed, ok := state.(ModelCacheFailed)
	if !ok {
		t.Fatalf("expected ModelCacheFailed, got %T", state)
	}
	if failed.ErrorMessage != mc.Status.ErrorMessage {
		t.Errorf("ErrorMessage: got %q, want %q", failed.ErrorMessage, mc.Status.ErrorMessage)
	}
	if failed.LastState != mc.Status.LastState {
		t.Errorf("LastState: got %q, want %q", failed.LastState, mc.Status.LastState)
	}
	if failed.Permanent != mc.Status.Permanent {
		t.Errorf("Permanent: got %v, want %v", failed.Permanent, mc.Status.Permanent)
	}
}

// Failed state Permanent=false is also mapped correctly (not just Permanent=true).
func TestCalculator_FailedPhase_PermanentFalse_IsMapped(t *testing.T) {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
		Status: v1alpha1.ModelCacheStatus{
			Phase:        PhaseFailed,
			ErrorMessage: "temporary network issue",
			LastState:    "Syncing",
			Permanent:    false,
		},
	}

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	failed, ok := state.(ModelCacheFailed)
	if !ok {
		t.Fatalf("expected ModelCacheFailed, got %T", state)
	}
	if failed.Permanent {
		t.Error("Permanent should be false for transient failures")
	}
}

// =============================================================================
// Transitions: all-field propagation through Resolved, CacheHit, SyncComplete
// =============================================================================

// Resolved carries FileCount, TotalSize, and Format to the new Resolving state.
func TestPending_Resolved_PropagatesAllFields(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	resolving := pending.Resolved(
		"ghcr.io/jomcgi/models/llama:main",
		"sha256:abc123",
		"rev-main",
		"safetensors",
		13,
		8589934592,
	)

	if resolving.Format != "safetensors" {
		t.Errorf("Format: got %q, want safetensors", resolving.Format)
	}
	if resolving.FileCount != 13 {
		t.Errorf("FileCount: got %d, want 13", resolving.FileCount)
	}
	if resolving.TotalSize != 8589934592 {
		t.Errorf("TotalSize: got %d, want 8589934592", resolving.TotalSize)
	}
	if resolving.ResolvedRevision != "rev-main" {
		t.Errorf("ResolvedRevision: got %q, want rev-main", resolving.ResolvedRevision)
	}
	if resolving.Resource() != mc {
		t.Error("resource pointer not propagated through Resolved transition")
	}
}

// CacheHit carries all fields including FileCount, TotalSize, and Format.
func TestPending_CacheHit_PropagatesAllFields(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	ready := pending.CacheHit(
		"ghcr.io/jomcgi/models/llama:main",
		"sha256:final",
		"rev-main",
		"gguf",
		2,
		4294967296,
	)

	if ready.FileCount != 2 {
		t.Errorf("FileCount: got %d, want 2", ready.FileCount)
	}
	if ready.TotalSize != 4294967296 {
		t.Errorf("TotalSize: got %d, want 4294967296", ready.TotalSize)
	}
	if ready.Format != "gguf" {
		t.Errorf("Format: got %q, want gguf", ready.Format)
	}
	if ready.ResolvedRevision != "rev-main" {
		t.Errorf("ResolvedRevision: got %q, want rev-main", ready.ResolvedRevision)
	}
	if ready.Resource() != mc {
		t.Error("resource pointer not propagated through CacheHit transition")
	}
}

// JobCreated carries ALL ResolveResult fields (including Digest) from Resolving → Syncing.
func TestResolving_JobCreated_CarriesAllResolveFields(t *testing.T) {
	mc := newMC(PhaseResolving)
	resolving := ModelCacheResolving{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			Digest:           "sha256:pre-push",
			ResolvedRevision: "rev-abc",
			Format:           "safetensors",
			FileCount:        5,
			TotalSize:        1000000,
		},
	}

	syncing := resolving.JobCreated("sync-job-123")

	if syncing.SyncJobName != "sync-job-123" {
		t.Errorf("SyncJobName: got %q, want sync-job-123", syncing.SyncJobName)
	}
	if syncing.ResolvedRef != resolving.ResolvedRef {
		t.Errorf("ResolvedRef not carried: got %q", syncing.ResolvedRef)
	}
	if syncing.Digest != resolving.Digest {
		t.Errorf("Digest not carried: got %q", syncing.Digest)
	}
	if syncing.ResolvedRevision != resolving.ResolvedRevision {
		t.Errorf("ResolvedRevision not carried: got %q", syncing.ResolvedRevision)
	}
	if syncing.Format != resolving.Format {
		t.Errorf("Format not carried: got %q", syncing.Format)
	}
	if syncing.FileCount != resolving.FileCount {
		t.Errorf("FileCount not carried: got %d", syncing.FileCount)
	}
	if syncing.TotalSize != resolving.TotalSize {
		t.Errorf("TotalSize not carried: got %d", syncing.TotalSize)
	}
	if syncing.Resource() != mc {
		t.Error("resource pointer not propagated through JobCreated transition")
	}
}

// SyncComplete maps all parameters including FileCount and TotalSize to the Ready state.
func TestSyncing_SyncComplete_PropagatesAllFields(t *testing.T) {
	mc := newMC(PhaseSyncing)
	syncing := ModelCacheSyncing{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "old-ref", ResolvedRevision: "main", Format: "gguf"},
		SyncJob:       SyncJob{SyncJobName: "sync-job"},
	}

	ready := syncing.SyncComplete(
		"ghcr.io/jomcgi/models/llama:main",
		"sha256:post-push-digest",
		"rev-main",
		"safetensors",
		9,
		7654321098,
	)

	if ready.ResolvedRef != "ghcr.io/jomcgi/models/llama:main" {
		t.Errorf("ResolvedRef: got %q", ready.ResolvedRef)
	}
	if ready.Digest != "sha256:post-push-digest" {
		t.Errorf("Digest: got %q", ready.Digest)
	}
	if ready.ResolvedRevision != "rev-main" {
		t.Errorf("ResolvedRevision: got %q", ready.ResolvedRevision)
	}
	if ready.Format != "safetensors" {
		t.Errorf("Format: got %q", ready.Format)
	}
	if ready.FileCount != 9 {
		t.Errorf("FileCount: got %d, want 9", ready.FileCount)
	}
	if ready.TotalSize != 7654321098 {
		t.Errorf("TotalSize: got %d, want 7654321098", ready.TotalSize)
	}
	if ready.Resource() != mc {
		t.Error("resource pointer not propagated through SyncComplete")
	}
}

// =============================================================================
// Transitions: resource pointer propagation through every transition method
// =============================================================================

// Every transition method must carry the resource pointer forward so the
// controller can always call state.Resource() to get the original CR.
func TestTransitions_ResourcePointerPropagation(t *testing.T) {
	mc := newMC(PhasePending)

	// Pending.MarkFailed
	pendingFailed := ModelCachePending{resource: mc}.MarkFailed("err", false, "Pending")
	if pendingFailed.Resource() != mc {
		t.Error("Pending.MarkFailed: resource not propagated")
	}

	// Resolving.MarkFailed
	resolving := ModelCacheResolving{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
	}
	resolvingFailed := resolving.MarkFailed("err", false, "Resolving")
	if resolvingFailed.Resource() != mc {
		t.Error("Resolving.MarkFailed: resource not propagated")
	}

	// Syncing.MarkFailed
	syncing := ModelCacheSyncing{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
		SyncJob:       SyncJob{SyncJobName: "job"},
	}
	syncingFailed := syncing.MarkFailed("err", false, "Syncing")
	if syncingFailed.Resource() != mc {
		t.Error("Syncing.MarkFailed: resource not propagated")
	}

	// Ready.Resync
	ready := ModelCacheReady{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef: "ref", Digest: "sha256:abc", ResolvedRevision: "main", Format: "safetensors",
		},
	}
	resyncPending := ready.Resync()
	if resyncPending.Resource() != mc {
		t.Error("Ready.Resync: resource not propagated")
	}

	// Failed.Retry (transient)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: false, LastState: "Pending", ErrorMessage: "transient"},
	}
	retryPending := failed.Retry()
	if retryPending == nil {
		t.Fatal("Retry() should return non-nil for transient error")
	}
	if retryPending.Resource() != mc {
		t.Error("Failed.Retry: resource not propagated")
	}

	// Unknown.Reset
	unknown := ModelCacheUnknown{resource: mc, ObservedPhase: "Pending"}
	resetPending := unknown.Reset()
	if resetPending.Resource() != mc {
		t.Error("Unknown.Reset: resource not propagated")
	}
}

// =============================================================================
// Visit: FuncVisitor specific handler for each state prevents Default from firing
// =============================================================================

// For each of the 5 remaining states (non-Pending), verify that setting the
// specific On* handler suppresses Default.
func TestFuncVisitor_SpecificHandlerPreventsDefaultForEachState(t *testing.T) {
	mc := newMC("")

	tests := []struct {
		name    string
		state   ModelCacheState
		visitor *ModelCacheFuncVisitor[string]
		want    string
	}{
		{
			name:  "OnResolving takes precedence over Default",
			state: ModelCacheResolving{resource: mc},
			visitor: &ModelCacheFuncVisitor[string]{
				OnResolving: func(_ ModelCacheResolving) string { return "resolving-specific" },
				Default:     func(_ ModelCacheState) string { return "default" },
			},
			want: "resolving-specific",
		},
		{
			name:  "OnSyncing takes precedence over Default",
			state: ModelCacheSyncing{resource: mc},
			visitor: &ModelCacheFuncVisitor[string]{
				OnSyncing: func(_ ModelCacheSyncing) string { return "syncing-specific" },
				Default:   func(_ ModelCacheState) string { return "default" },
			},
			want: "syncing-specific",
		},
		{
			name:  "OnReady takes precedence over Default",
			state: ModelCacheReady{resource: mc},
			visitor: &ModelCacheFuncVisitor[string]{
				OnReady: func(_ ModelCacheReady) string { return "ready-specific" },
				Default: func(_ ModelCacheState) string { return "default" },
			},
			want: "ready-specific",
		},
		{
			name:  "OnFailed takes precedence over Default",
			state: ModelCacheFailed{resource: mc},
			visitor: &ModelCacheFuncVisitor[string]{
				OnFailed: func(_ ModelCacheFailed) string { return "failed-specific" },
				Default:  func(_ ModelCacheState) string { return "default" },
			},
			want: "failed-specific",
		},
		{
			name:  "OnUnknown takes precedence over Default",
			state: ModelCacheUnknown{resource: mc, ObservedPhase: "x"},
			visitor: &ModelCacheFuncVisitor[string]{
				OnUnknown: func(_ ModelCacheUnknown) string { return "unknown-specific" },
				Default:   func(_ ModelCacheState) string { return "default" },
			},
			want: "unknown-specific",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := Visit(tc.state, tc.visitor)
			if got != tc.want {
				t.Errorf("Visit(%T) = %q, want %q", tc.state, got, tc.want)
			}
		})
	}
}

// Default receives the actual state value as its argument so callers can
// inspect it (e.g. log the phase). Verify state identity is preserved.
func TestFuncVisitor_Default_ReceivesStateArgument(t *testing.T) {
	mc := newMC("")

	var received ModelCacheState
	visitor := &ModelCacheFuncVisitor[string]{
		Default: func(s ModelCacheState) string {
			received = s
			return s.Phase()
		},
	}

	state := ModelCacheReady{resource: mc}
	got := Visit[string](state, visitor)

	if got != PhaseReady {
		t.Errorf("Default returned %q, want %q", got, PhaseReady)
	}
	if received == nil {
		t.Fatal("Default did not receive the state argument")
	}
	if received.Phase() != PhaseReady {
		t.Errorf("received state phase = %q, want %q", received.Phase(), PhaseReady)
	}
}

// =============================================================================
// Phases: AllPhases order and IsKnownPhase near-miss strings
// =============================================================================

// AllPhases must return phases in the documented, stable order.
// Order matters when callers index into the slice for display/iteration.
func TestAllPhases_OrderIsDeterministic(t *testing.T) {
	want := []string{PhasePending, PhaseResolving, PhaseSyncing, PhaseReady, PhaseFailed, PhaseUnknown}
	got := AllPhases()
	if len(got) != len(want) {
		t.Fatalf("AllPhases() returned %d phases, want %d", len(got), len(want))
	}
	for i, phase := range want {
		if got[i] != phase {
			t.Errorf("AllPhases()[%d] = %q, want %q", i, got[i], phase)
		}
	}
}

// IsKnownPhase must reject strings that look like valid phases but differ by
// whitespace or case — preventing silent acceptance of malformed status values.
func TestIsKnownPhase_RejectsNearMisses(t *testing.T) {
	nearMisses := []string{
		" Pending",    // leading space
		"Pending ",    // trailing space
		"pending",     // wrong case
		"PENDING",     // all caps
		"Resolving\n", // trailing newline
		"\tSyncing",   // leading tab
		"ready",       // lowercase
		"FAILED",      // uppercase
	}
	for _, phase := range nearMisses {
		if IsKnownPhase(phase) {
			t.Errorf("IsKnownPhase(%q) = true; want false (near-miss string)", phase)
		}
	}
}

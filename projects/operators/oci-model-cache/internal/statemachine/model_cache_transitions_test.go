package statemachine

// Dedicated tests for model_cache_transitions.go.
//
// The shared test files (statemachine_test.go, model_cache_gaps_test.go,
// model_cache_missing_test.go) already cover the main happy paths and field
// propagation.  This file targets gaps that remain:
//
//   - MarkFailed from Resolving with Permanent=true (permanent failure)
//   - MarkFailed from Syncing with Permanent=true (permanent failure)
//   - Boundary values: zero FileCount and TotalSize across all transitions
//   - Idempotency: re-calling the same transition with the same parameters
//     produces an identical new state (deterministic, no side-effects)
//   - Reset() resource pointer is the same pointer (not a copy)

import (
	"testing"
	"time"
)

// =============================================================================
// MarkFailed from Resolving with Permanent=true
// =============================================================================

// When a Resolving state encounters a permanent error (e.g. unsupported format),
// MarkFailed must set Permanent=true in the Failed state.
func TestResolving_MarkFailed_Permanent_True(t *testing.T) {
	mc := newMC(PhaseResolving)
	resolving := ModelCacheResolving{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/test/model:latest",
			ResolvedRevision: "main",
			Format:           "unknown-format",
		},
	}

	failed := resolving.MarkFailed("unsupported model format", true, PhaseResolving)

	if failed.Phase() != PhaseFailed {
		t.Errorf("expected PhaseFailed, got %q", failed.Phase())
	}
	if !failed.Permanent {
		t.Error("Permanent must be true for a permanent failure from Resolving")
	}
	if failed.ErrorMessage != "unsupported model format" {
		t.Errorf("ErrorMessage = %q, want %q", failed.ErrorMessage, "unsupported model format")
	}
	if failed.LastState != PhaseResolving {
		t.Errorf("LastState = %q, want %q", failed.LastState, PhaseResolving)
	}
	if failed.Resource() != mc {
		t.Error("resource pointer must be propagated through Resolving.MarkFailed")
	}
}

// =============================================================================
// MarkFailed from Syncing with Permanent=true
// =============================================================================

// When a Syncing state encounters a permanent error (e.g. registry push rejected),
// MarkFailed must set Permanent=true and preserve the LastState as Syncing.
func TestSyncing_MarkFailed_Permanent_True(t *testing.T) {
	mc := newMC(PhaseSyncing)
	syncing := ModelCacheSyncing{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/test/model:latest",
			ResolvedRevision: "main",
			Format:           "safetensors",
		},
		SyncJob: SyncJob{SyncJobName: "sync-job-permanent"},
	}

	failed := syncing.MarkFailed("registry push permanently rejected", true, PhaseSyncing)

	if failed.Phase() != PhaseFailed {
		t.Errorf("expected PhaseFailed, got %q", failed.Phase())
	}
	if !failed.Permanent {
		t.Error("Permanent must be true for a permanent failure from Syncing")
	}
	if failed.ErrorMessage != "registry push permanently rejected" {
		t.Errorf("ErrorMessage = %q", failed.ErrorMessage)
	}
	if failed.LastState != PhaseSyncing {
		t.Errorf("LastState = %q, want %q", failed.LastState, PhaseSyncing)
	}
	if failed.Resource() != mc {
		t.Error("resource pointer must be propagated through Syncing.MarkFailed")
	}
}

// =============================================================================
// Boundary values: zero FileCount and TotalSize
// =============================================================================

// Resolved must accept zero FileCount and zero TotalSize — these are valid when
// the resolver has not yet computed size metadata (e.g. single-file models).
func TestPending_Resolved_ZeroBoundaryValues(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	resolving := pending.Resolved(
		"ghcr.io/test/model:latest",
		"sha256:deadbeef",
		"main",
		"gguf",
		0, // FileCount = 0 (boundary)
		0, // TotalSize = 0 (boundary)
	)

	if resolving.FileCount != 0 {
		t.Errorf("FileCount = %d, want 0", resolving.FileCount)
	}
	if resolving.TotalSize != 0 {
		t.Errorf("TotalSize = %d, want 0", resolving.TotalSize)
	}
	if err := resolving.Validate(); err != nil {
		// Validate only checks ResolvedRef, ResolvedRevision, Format — zero counts are OK.
		t.Errorf("Validate() failed unexpectedly: %v", err)
	}
}

// CacheHit must accept zero FileCount and zero TotalSize.
func TestPending_CacheHit_ZeroBoundaryValues(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	ready := pending.CacheHit(
		"ghcr.io/test/model:latest",
		"sha256:abc123",
		"main",
		"safetensors",
		0,
		0,
	)

	if ready.FileCount != 0 {
		t.Errorf("FileCount = %d, want 0", ready.FileCount)
	}
	if ready.TotalSize != 0 {
		t.Errorf("TotalSize = %d, want 0", ready.TotalSize)
	}
}

// SyncComplete must accept zero FileCount and zero TotalSize.
func TestSyncing_SyncComplete_ZeroBoundaryValues(t *testing.T) {
	mc := newMC(PhaseSyncing)
	syncing := ModelCacheSyncing{
		resource:      mc,
		ResolveResult: ResolveResult{ResolvedRef: "ref", ResolvedRevision: "main", Format: "gguf"},
		SyncJob:       SyncJob{SyncJobName: "sync-job"},
	}

	ready := syncing.SyncComplete(
		"ghcr.io/test/model:latest",
		"sha256:final",
		"main",
		"gguf",
		0,
		0,
	)

	if ready.FileCount != 0 {
		t.Errorf("FileCount = %d, want 0", ready.FileCount)
	}
	if ready.TotalSize != 0 {
		t.Errorf("TotalSize = %d, want 0", ready.TotalSize)
	}
}

// =============================================================================
// Idempotency: deterministic transitions produce identical state
// =============================================================================

// Calling Resolved with the same parameters twice must produce states with
// identical field values (no random IDs generated internally, no side-effects).
func TestPending_Resolved_IsDeterministic(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	args := [6]interface{}{"ghcr.io/test/model:latest", "sha256:abc", "main", "gguf", 3, int64(1024)}
	r1 := pending.Resolved(args[0].(string), args[1].(string), args[2].(string), args[3].(string), args[4].(int), args[5].(int64))
	r2 := pending.Resolved(args[0].(string), args[1].(string), args[2].(string), args[3].(string), args[4].(int), args[5].(int64))

	if r1.ResolvedRef != r2.ResolvedRef || r1.Digest != r2.Digest || r1.Format != r2.Format {
		t.Error("Resolved is not deterministic: repeated calls with same args produced different states")
	}
}

// Calling MarkFailed with the same parameters twice must produce identical states.
func TestPending_MarkFailed_IsDeterministic(t *testing.T) {
	mc := newMC(PhasePending)
	pending := ModelCachePending{resource: mc}

	f1 := pending.MarkFailed("timeout", false, PhasePending)
	f2 := pending.MarkFailed("timeout", false, PhasePending)

	if f1.ErrorMessage != f2.ErrorMessage || f1.Permanent != f2.Permanent || f1.LastState != f2.LastState {
		t.Error("MarkFailed is not deterministic: repeated calls with same args produced different states")
	}
}

// =============================================================================
// Retry guard: guard condition details
// =============================================================================

// The guard condition in Retry() is `!(!s.Permanent)` which evaluates to
// `s.Permanent`.  When Permanent=false, the guard fails (doesn't return nil),
// and Retry returns a valid Pending state.  This is already tested elsewhere
// but we verify the guard boundary explicitly by testing both values.
func TestFailed_Retry_GuardBoundary(t *testing.T) {
	mc := newMC(PhaseFailed)

	cases := []struct {
		permanent bool
		wantNil   bool
	}{
		{permanent: false, wantNil: false}, // transient: Retry succeeds
		{permanent: true, wantNil: true},   // permanent: Retry returns nil
	}

	for _, tc := range cases {
		tc := tc
		t.Run("permanent="+boolStr(tc.permanent), func(t *testing.T) {
			failed := ModelCacheFailed{
				resource:  mc,
				ErrorInfo: ErrorInfo{Permanent: tc.permanent, LastState: "Pending", ErrorMessage: "err"},
			}
			result := failed.Retry()
			if tc.wantNil && result != nil {
				t.Errorf("expected nil, got %+v", result)
			}
			if !tc.wantNil && result == nil {
				t.Error("expected non-nil Pending, got nil")
			}
		})
	}
}

// =============================================================================
// RetryBackoff values
// =============================================================================

// Unknown.RetryBackoff() must return exactly 30 seconds (30_000_000_000 ns).
// This guards against accidental changes to the hardcoded constant.
func TestUnknown_RetryBackoff_ExactValue(t *testing.T) {
	unknown := ModelCacheUnknown{resource: newMC("bad"), ObservedPhase: "bad"}
	const want = 30 * time.Second
	got := unknown.RetryBackoff()
	if got != want {
		t.Errorf("Unknown.RetryBackoff() = %v, want %v", got, want)
	}
}

// Failed.RetryBackoff() must equal Failed.RequeueAfter() by definition.
func TestFailed_RetryBackoff_EqualToRequeueAfter(t *testing.T) {
	mc := newMC(PhaseFailed)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: false, LastState: "Pending", ErrorMessage: "err"},
	}
	backoff := failed.RetryBackoff()
	requeue := failed.RequeueAfter()
	if backoff != requeue {
		t.Errorf("RetryBackoff() = %v, RequeueAfter() = %v; they must be equal", backoff, requeue)
	}
}

// =============================================================================
// Reset: resource pointer identity
// =============================================================================

// Unknown.Reset() must return the same resource pointer (not a deep copy).
func TestUnknown_Reset_ResourcePointerIdentity(t *testing.T) {
	mc := newMC("garbage")
	unknown := ModelCacheUnknown{resource: mc, ObservedPhase: "garbage"}
	pending := unknown.Reset()
	if pending.Resource() != mc {
		t.Error("Reset() must carry the original resource pointer forward")
	}
}

// =============================================================================
// helpers
// =============================================================================

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

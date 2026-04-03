package statemachine

import (
	"testing"
	"time"

	"github.com/go-logr/logr/testr"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// --- Calculator: PhaseSyncing with corrupt status falls back to Unknown ---

func TestCalculator_SyncingPhase_MissingSyncJobName_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{}
	mc.Name = "test"
	mc.Namespace = "default"
	mc.Status.Phase = PhaseSyncing
	mc.Status.ResolvedRef = "ghcr.io/jomcgi/models/llama:main"
	mc.Status.ResolvedRevision = "main"
	mc.Status.Format = "safetensors"
	// SyncJobName intentionally empty → SyncJob.Validate() fails

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Errorf("expected ModelCacheUnknown due to missing SyncJobName, got %T", state)
	}
	if unknown.ObservedPhase != PhaseSyncing {
		t.Errorf("expected ObservedPhase=%q, got %q", PhaseSyncing, unknown.ObservedPhase)
	}
}

func TestCalculator_SyncingPhase_MissingResolveResult_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{}
	mc.Name = "test"
	mc.Namespace = "default"
	mc.Status.Phase = PhaseSyncing
	mc.Status.SyncJobName = "sync-job-abc"
	// ResolvedRef empty → ResolveResult.Validate() fails

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheUnknown); !ok {
		t.Errorf("expected ModelCacheUnknown due to missing ResolveResult, got %T", state)
	}
}

// --- Calculator: PhaseReady with corrupt status falls back to Unknown ---

func TestCalculator_ReadyPhase_MissingDigest_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{}
	mc.Name = "test"
	mc.Namespace = "default"
	mc.Status.Phase = PhaseReady
	mc.Status.ResolvedRef = "ghcr.io/jomcgi/models/llama:main"
	mc.Status.ResolvedRevision = "main"
	mc.Status.Format = "safetensors"
	// Digest intentionally empty → ModelCacheReady.Validate() fails

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	unknown, ok := state.(ModelCacheUnknown)
	if !ok {
		t.Errorf("expected ModelCacheUnknown due to missing Digest, got %T", state)
	}
	if unknown.ObservedPhase != PhaseReady {
		t.Errorf("expected ObservedPhase=%q, got %q", PhaseReady, unknown.ObservedPhase)
	}
}

func TestCalculator_ReadyPhase_MissingResolvedRef_FallsBackToUnknown(t *testing.T) {
	mc := &v1alpha1.ModelCache{}
	mc.Name = "test"
	mc.Namespace = "default"
	mc.Status.Phase = PhaseReady
	mc.Status.Digest = "sha256:abc123"
	mc.Status.ResolvedRevision = "main"
	mc.Status.Format = "safetensors"
	// ResolvedRef empty → ResolveResult.Validate() fails

	calc := NewModelCacheCalculator(testr.New(t))
	state := calc.Calculate(mc)

	if _, ok := state.(ModelCacheUnknown); !ok {
		t.Errorf("expected ModelCacheUnknown due to missing ResolvedRef, got %T", state)
	}
}

// --- SyncJob.Validate() ---

func TestSyncJob_Validate_Success(t *testing.T) {
	s := SyncJob{SyncJobName: "sync-job-abc"}
	if err := s.Validate(); err != nil {
		t.Errorf("expected Validate() to succeed, got: %v", err)
	}
}

func TestSyncJob_Validate_MissingSyncJobName(t *testing.T) {
	s := SyncJob{}
	err := s.Validate()
	if err == nil {
		t.Error("expected Validate() to fail when SyncJobName is empty")
	}
	const want = "syncJobName"
	if err != nil && !containsSubstring(err.Error(), want) {
		t.Errorf("expected error to mention %q, got: %v", want, err)
	}
}

// --- ErrorInfo.Validate() with error-ordering check ---

func TestErrorInfo_Validate_Success(t *testing.T) {
	e := ErrorInfo{
		LastState:    "Pending",
		ErrorMessage: "connection refused",
	}
	if err := e.Validate(); err != nil {
		t.Errorf("expected Validate() to succeed, got: %v", err)
	}
}

func TestErrorInfo_Validate_ErrorOrdering(t *testing.T) {
	cases := []struct {
		name          string
		info          ErrorInfo
		wantSubstring string
	}{
		{
			name:          "missing LastState is checked first",
			info:          ErrorInfo{ErrorMessage: "boom"}, // LastState empty
			wantSubstring: "lastState",
		},
		{
			name:          "missing ErrorMessage reported when LastState is present",
			info:          ErrorInfo{LastState: "Pending"}, // ErrorMessage empty
			wantSubstring: "errorMessage",
		},
		{
			name:          "both missing: LastState error returned first",
			info:          ErrorInfo{},
			wantSubstring: "lastState",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := tc.info.Validate()
			if err == nil {
				t.Fatal("expected a validation error, got nil")
			}
			if !containsSubstring(err.Error(), tc.wantSubstring) {
				t.Errorf("expected error to mention %q, got: %v", tc.wantSubstring, err)
			}
		})
	}
}

// --- RetryBackoff constants ---

func TestFailed_RetryBackoff_Is300Seconds(t *testing.T) {
	mc := newMC(PhaseFailed)
	failed := ModelCacheFailed{
		resource:  mc,
		ErrorInfo: ErrorInfo{Permanent: false, LastState: "Pending", ErrorMessage: "err"},
	}
	want := 300 * time.Second
	got := failed.RetryBackoff()
	if got != want {
		t.Errorf("Failed.RetryBackoff() = %v, want %v", got, want)
	}
	// Also verify it equals RequeueAfter (the documented invariant)
	if got != failed.RequeueAfter() {
		t.Errorf("Failed.RetryBackoff() = %v, want it to equal RequeueAfter() = %v", got, failed.RequeueAfter())
	}
}

func TestUnknown_RetryBackoff_Is30Seconds(t *testing.T) {
	unknown := ModelCacheUnknown{resource: newMC("garbage"), ObservedPhase: "garbage"}
	want := 30 * time.Second
	got := unknown.RetryBackoff()
	if got != want {
		t.Errorf("Unknown.RetryBackoff() = %v, want %v", got, want)
	}
}

// --- helpers ---

// containsSubstring reports whether s contains substr (avoids importing strings).
func containsSubstring(s, substr string) bool {
	if len(substr) == 0 {
		return true
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

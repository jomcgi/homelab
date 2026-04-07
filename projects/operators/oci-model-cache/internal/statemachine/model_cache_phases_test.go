package statemachine

// Dedicated tests for model_cache_phases.go.
//
// The shared test files already verify:
//   - IsKnownPhase returns true for all valid phases (statemachine_test.go)
//   - IsKnownPhase rejects near-miss strings (model_cache_gaps_test.go)
//   - AllPhases() contains the expected phases (statemachine_test.go)
//   - AllPhases() returns them in deterministic order (model_cache_gaps_test.go)
//
// This file adds:
//   - Exact string value assertions for each phase constant (typo guard)
//   - AllPhases() slice mutation safety (caller can mutate returned slice
//     without affecting future AllPhases() calls)
//   - IsKnownPhase for every edge case: empty string (initial state), all six
//     named phases, and a distinct set of invalid strings not tested elsewhere.

import (
	"testing"
)

// =============================================================================
// Phase constant exact values
// =============================================================================

// Each constant must equal its documented string value.
// This guards against silent typos in generated code (e.g. "Resoving" instead of "Resolving").
func TestPhaseConstants_ExactStringValues(t *testing.T) {
	cases := []struct {
		name     string
		got      string
		wantExact string
	}{
		{"PhasePending", PhasePending, "Pending"},
		{"PhaseResolving", PhaseResolving, "Resolving"},
		{"PhaseSyncing", PhaseSyncing, "Syncing"},
		{"PhaseReady", PhaseReady, "Ready"},
		{"PhaseFailed", PhaseFailed, "Failed"},
		{"PhaseUnknown", PhaseUnknown, "Unknown"},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			if tc.got != tc.wantExact {
				t.Errorf("%s = %q, want %q", tc.name, tc.got, tc.wantExact)
			}
		})
	}
}

// =============================================================================
// AllPhases() slice mutation safety
// =============================================================================

// AllPhases() must return a new slice each time so that a caller modifying the
// returned slice does not affect subsequent calls.
func TestAllPhases_MutationSafe(t *testing.T) {
	first := AllPhases()
	if len(first) == 0 {
		t.Fatal("AllPhases() returned an empty slice")
	}

	// Corrupt the first returned slice.
	original := first[0]
	first[0] = "corrupted"

	second := AllPhases()
	if len(second) == 0 {
		t.Fatal("AllPhases() returned an empty slice after mutation")
	}
	if second[0] == "corrupted" {
		t.Errorf("AllPhases() returned the same underlying slice; "+
			"mutating the first call's result corrupted the second call (got %q, want %q)",
			second[0], original)
	}
	if second[0] != original {
		t.Errorf("AllPhases()[0] = %q after mutation experiment, want %q", second[0], original)
	}
}

// AllPhases() must return exactly 6 phases.
func TestAllPhases_HasExactlyFivePhases(t *testing.T) {
	const want = 6
	got := len(AllPhases())
	if got != want {
		t.Errorf("AllPhases() returned %d phases, want %d", got, want)
	}
}

// =============================================================================
// IsKnownPhase: comprehensive valid inputs
// =============================================================================

// Every value returned by AllPhases() must be recognized by IsKnownPhase.
func TestIsKnownPhase_AcceptsAllPhasesReturnValues(t *testing.T) {
	for _, phase := range AllPhases() {
		phase := phase
		t.Run(phase, func(t *testing.T) {
			if !IsKnownPhase(phase) {
				t.Errorf("IsKnownPhase(%q) = false; must be true for phases returned by AllPhases()", phase)
			}
		})
	}
}

// Empty string is the documented initial state and must be accepted.
func TestIsKnownPhase_EmptyStringIsInitialState(t *testing.T) {
	if !IsKnownPhase("") {
		t.Error("IsKnownPhase(\"\") = false; empty string represents the initial state and must be accepted")
	}
}

// =============================================================================
// IsKnownPhase: invalid inputs distinct from those in model_cache_gaps_test.go
// =============================================================================

// These invalid strings are different from the near-misses in model_cache_gaps_test.go
// to avoid duplication while still verifying the default branch is reachable.
func TestIsKnownPhase_RejectsUnrelatedStrings(t *testing.T) {
	invalids := []string{
		"active",        // different domain entirely
		"running",       // Kubernetes pod phase, not ours
		"completed",     // job phase, not a ModelCache phase
		"terminating",   // Kubernetes namespace phase
		"null",          // JSON null as a string
		"0",             // number
		"true",          // boolean
		"  ",            // whitespace only
	}
	for _, phase := range invalids {
		phase := phase
		t.Run(phase, func(t *testing.T) {
			if IsKnownPhase(phase) {
				t.Errorf("IsKnownPhase(%q) = true; want false", phase)
			}
		})
	}
}

// =============================================================================
// Phase constants: each appears exactly once in AllPhases()
// =============================================================================

// Each named phase constant must appear exactly once in AllPhases().
// Duplicates would break code that uses the slice for display or iteration.
func TestAllPhases_NoDuplicates(t *testing.T) {
	seen := make(map[string]int)
	for _, p := range AllPhases() {
		seen[p]++
	}
	for phase, count := range seen {
		if count != 1 {
			t.Errorf("phase %q appears %d times in AllPhases(), want exactly 1", phase, count)
		}
	}
}

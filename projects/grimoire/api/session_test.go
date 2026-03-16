package main

import "testing"

// TestValidSessionTransitions_AllowedPaths verifies the validTransitions map permits
// all expected session state transitions.
func TestValidSessionTransitions_AllowedPaths(t *testing.T) {
	allowed := []struct{ from, to string }{
		{"planning", "active"},  // start
		{"active", "paused"},    // pause
		{"active", "completed"}, // end directly from active
		{"paused", "active"},    // resume
		{"paused", "completed"}, // end from paused
	}
	for _, tc := range allowed {
		states, ok := validTransitions[tc.from]
		if !ok {
			t.Errorf("no transitions defined for state %q", tc.from)
			continue
		}
		if !states[tc.to] {
			t.Errorf("expected allowed transition %q -> %q", tc.from, tc.to)
		}
	}
}

// TestValidSessionTransitions_ForbiddenPaths verifies the validTransitions map blocks
// all disallowed session state transitions.
func TestValidSessionTransitions_ForbiddenPaths(t *testing.T) {
	forbidden := []struct{ from, to string }{
		{"planning", "completed"}, // must pass through active
		{"planning", "paused"},    // cannot jump directly to paused
		{"active", "planning"},    // no reverting back to planning
		{"completed", "active"},   // completed is a terminal state
		{"completed", "planning"}, // terminal state
		{"completed", "paused"},   // terminal state
	}
	for _, tc := range forbidden {
		states, ok := validTransitions[tc.from]
		if !ok {
			continue // state has no transitions at all — correctly forbidden
		}
		if states[tc.to] {
			t.Errorf("expected forbidden transition %q -> %q to be absent", tc.from, tc.to)
		}
	}
}

// TestValidSessionTransitions_CompletedHasNoTransitions verifies the completed state
// cannot transition to anything.
func TestValidSessionTransitions_CompletedHasNoTransitions(t *testing.T) {
	if _, ok := validTransitions["completed"]; ok {
		t.Error("completed state should have no outgoing transitions")
	}
}

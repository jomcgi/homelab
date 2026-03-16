package main

import "testing"

// TestValidEncounterTransition_Valid verifies all permitted encounter state transitions.
func TestValidEncounterTransition_Valid(t *testing.T) {
	cases := []struct {
		from, to string
	}{
		{"planned", "active"},
		{"active", "completed"},
	}
	for _, tc := range cases {
		if !validEncounterTransition(tc.from, tc.to) {
			t.Errorf("expected valid transition: %q -> %q", tc.from, tc.to)
		}
	}
}

// TestValidEncounterTransition_Invalid verifies that invalid transitions are rejected.
func TestValidEncounterTransition_Invalid(t *testing.T) {
	cases := []struct {
		from, to string
	}{
		{"planned", "completed"},  // must pass through active
		{"planned", "planned"},    // no self-transitions
		{"active", "planned"},     // no reverting
		{"active", "active"},      // no self-transitions
		{"completed", "active"},   // completed is a terminal state
		{"completed", "planned"},  // completed is a terminal state
		{"completed", "completed"},
		{"", "active"},   // unknown from state
		{"active", ""},   // unknown to state
		{"unknown", "active"},
	}
	for _, tc := range cases {
		if validEncounterTransition(tc.from, tc.to) {
			t.Errorf("expected invalid transition: %q -> %q", tc.from, tc.to)
		}
	}
}

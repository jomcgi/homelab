package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// Severity constants
// ---------------------------------------------------------------------------

// TestSeverityConstants verifies that each Severity constant resolves to the
// documented string value used in JSON payloads and log messages.
func TestSeverityConstants(t *testing.T) {
	cases := []struct {
		got  Severity
		want string
	}{
		{SeverityInfo, "info"},
		{SeverityWarning, "warning"},
		{SeverityCritical, "critical"},
	}
	for _, tc := range cases {
		if string(tc.got) != tc.want {
			t.Errorf("Severity constant: got %q, want %q", tc.got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// ActionType constants
// ---------------------------------------------------------------------------

// TestActionTypeConstants verifies that each ActionType constant resolves to
// the documented string value used in JSON payloads.
func TestActionTypeConstants(t *testing.T) {
	cases := []struct {
		got  ActionType
		want string
	}{
		{ActionLog, "log"},
		{ActionOrchestratorJob, "orchestrator_job"},
	}
	for _, tc := range cases {
		if string(tc.got) != tc.want {
			t.Errorf("ActionType constant: got %q, want %q", tc.got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// Finding JSON roundtrip
// ---------------------------------------------------------------------------

// TestFindingJSONRoundtrip verifies that a fully-populated Finding survives a
// marshal → unmarshal cycle with all fields intact.
func TestFindingJSONRoundtrip(t *testing.T) {
	ts := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	original := Finding{
		Fingerprint: "abc123",
		Source:      "collector-alerts",
		Severity:    SeverityWarning,
		Title:       "High pod restarts",
		Detail:      "pod foo/bar restarted 10 times",
		Data:        map[string]any{"count": float64(10), "pod": "foo/bar"},
		Timestamp:   ts,
	}

	b, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}

	var got Finding
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if got.Fingerprint != original.Fingerprint {
		t.Errorf("Fingerprint: got %q, want %q", got.Fingerprint, original.Fingerprint)
	}
	if got.Source != original.Source {
		t.Errorf("Source: got %q, want %q", got.Source, original.Source)
	}
	if got.Severity != original.Severity {
		t.Errorf("Severity: got %q, want %q", got.Severity, original.Severity)
	}
	if got.Title != original.Title {
		t.Errorf("Title: got %q, want %q", got.Title, original.Title)
	}
	if got.Detail != original.Detail {
		t.Errorf("Detail: got %q, want %q", got.Detail, original.Detail)
	}
	if !got.Timestamp.Equal(original.Timestamp) {
		t.Errorf("Timestamp: got %v, want %v", got.Timestamp, original.Timestamp)
	}
	if len(got.Data) != len(original.Data) {
		t.Errorf("Data length: got %d, want %d", len(got.Data), len(original.Data))
	}
}

// TestFindingOmitsDataWhenNil verifies that the Data field is absent from the
// JSON output when it is nil (omitempty semantics).
func TestFindingOmitsDataWhenNil(t *testing.T) {
	f := Finding{
		Fingerprint: "fp1",
		Source:      "src",
		Severity:    SeverityInfo,
		Title:       "title",
		Detail:      "detail",
		Timestamp:   time.Now(),
		// Data intentionally omitted (nil)
	}

	b, err := json.Marshal(f)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b, &raw); err != nil {
		t.Fatalf("json.Unmarshal raw: %v", err)
	}

	if _, present := raw["data"]; present {
		t.Error("expected 'data' key to be absent when Data is nil, but it was present")
	}
}

// TestFindingIncludesDataWhenSet verifies that the Data field is present in
// the JSON output when it holds at least one entry.
func TestFindingIncludesDataWhenSet(t *testing.T) {
	f := Finding{
		Fingerprint: "fp2",
		Source:      "src",
		Severity:    SeverityCritical,
		Title:       "title",
		Detail:      "detail",
		Data:        map[string]any{"key": "value"},
		Timestamp:   time.Now(),
	}

	b, err := json.Marshal(f)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b, &raw); err != nil {
		t.Fatalf("json.Unmarshal raw: %v", err)
	}

	if _, present := raw["data"]; !present {
		t.Error("expected 'data' key to be present when Data has entries, but it was absent")
	}
}

// ---------------------------------------------------------------------------
// Action JSON roundtrip
// ---------------------------------------------------------------------------

// TestActionJSONRoundtrip verifies that a fully-populated Action survives a
// marshal → unmarshal cycle with all fields intact.
func TestActionJSONRoundtrip(t *testing.T) {
	original := Action{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "fp3",
			Source:      "rules-agent",
			Severity:    SeverityCritical,
			Title:       "disk full",
			Detail:      "node /dev/sda1 at 99%",
			Timestamp:   time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
		},
		Payload: map[string]any{"job": "disk-cleanup", "node": "worker-1"},
	}

	b, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}

	var got Action
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if got.Type != original.Type {
		t.Errorf("Type: got %q, want %q", got.Type, original.Type)
	}
	if got.Finding.Fingerprint != original.Finding.Fingerprint {
		t.Errorf("Finding.Fingerprint: got %q, want %q", got.Finding.Fingerprint, original.Finding.Fingerprint)
	}
	if got.Finding.Severity != original.Finding.Severity {
		t.Errorf("Finding.Severity: got %q, want %q", got.Finding.Severity, original.Finding.Severity)
	}
	if len(got.Payload) != len(original.Payload) {
		t.Errorf("Payload length: got %d, want %d", len(got.Payload), len(original.Payload))
	}
}

// TestActionOmitsPayloadWhenNil verifies that the Payload field is absent from
// JSON output when it is nil (omitempty semantics).
func TestActionOmitsPayloadWhenNil(t *testing.T) {
	a := Action{
		Type: ActionLog,
		Finding: Finding{
			Fingerprint: "fp4",
			Source:      "src",
			Severity:    SeverityInfo,
			Title:       "t",
			Detail:      "d",
			Timestamp:   time.Now(),
		},
		// Payload intentionally omitted (nil)
	}

	b, err := json.Marshal(a)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b, &raw); err != nil {
		t.Fatalf("json.Unmarshal raw: %v", err)
	}

	if _, present := raw["payload"]; present {
		t.Error("expected 'payload' key to be absent when Payload is nil, but it was present")
	}
}

// ---------------------------------------------------------------------------
// Agent interface — compile-time compliance check
// ---------------------------------------------------------------------------

// mockAgent is a minimal implementation of the Agent interface used solely to
// assert compile-time compliance. If Agent gains or changes methods, this file
// will fail to compile, surfacing the gap immediately.
type mockAgent struct {
	name     string
	interval time.Duration
}

func (m *mockAgent) Name() string { return m.name }
func (m *mockAgent) Interval() time.Duration { return m.interval }
func (m *mockAgent) Collect(_ context.Context) ([]Finding, error) {
	return nil, nil
}
func (m *mockAgent) Analyze(_ context.Context, _ []Finding) ([]Action, error) {
	return nil, nil
}
func (m *mockAgent) Execute(_ context.Context, _ []Action) error {
	return nil
}

// Compile-time assertion: *mockAgent must satisfy the Agent interface.
var _ Agent = (*mockAgent)(nil)

// TestMockAgentSatisfiesAgentInterface is a runtime sanity-check that
// complements the compile-time assertion above.
func TestMockAgentSatisfiesAgentInterface(t *testing.T) {
	var a Agent = &mockAgent{name: "mock", interval: time.Minute}

	if a.Name() != "mock" {
		t.Errorf("Name(): got %q, want %q", a.Name(), "mock")
	}
	if a.Interval() != time.Minute {
		t.Errorf("Interval(): got %v, want %v", a.Interval(), time.Minute)
	}

	findings, err := a.Collect(context.Background())
	if err != nil {
		t.Errorf("Collect: unexpected error: %v", err)
	}
	if findings != nil {
		t.Errorf("Collect: got %v, want nil", findings)
	}

	actions, err := a.Analyze(context.Background(), nil)
	if err != nil {
		t.Errorf("Analyze: unexpected error: %v", err)
	}
	if actions != nil {
		t.Errorf("Analyze: got %v, want nil", actions)
	}

	if err := a.Execute(context.Background(), nil); err != nil {
		t.Errorf("Execute: unexpected error: %v", err)
	}
}

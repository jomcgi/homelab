package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPatrolAgent_AnalyzeConvertsAllFindingsToJobs(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "patrol.alert.1",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": "1"},
		},
		{
			Fingerprint: "patrol.alert.2",
			Severity:    SeverityWarning,
			Title:       "High Error Rate",
			Data:        map[string]any{"rule_id": "2"},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}

	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}
	for i, action := range actions {
		if action.Type != ActionOrchestratorJob {
			t.Errorf("action[%d]: expected orchestrator_job, got %s", i, action.Type)
		}
	}
}

func TestPatrolAgent_AnalyzeEmptyFindings(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	actions, err := patrol.Analyze(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 0 {
		t.Errorf("expected 0 actions for empty findings, got %d", len(actions))
	}
}

func TestPatrolAgent_AnalyzePayloadContainsAlertNameSeverityRuleID(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "patrol.alert.fp",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Detail:      "container nginx in pod web-1 was OOMKilled",
			Data:        map[string]any{"rule_id": "42"},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}

	task, ok := actions[0].Payload["task"].(string)
	if !ok {
		t.Fatalf("expected Payload[\"task\"] to be a string, got %T", actions[0].Payload["task"])
	}

	for _, want := range []string{"Pod OOMKilled", "critical", "42", "container nginx in pod web-1 was OOMKilled"} {
		if !strings.Contains(task, want) {
			t.Errorf("Payload[\"task\"] missing %q:\n%s", want, task)
		}
	}
}

func TestPatrolAgent_AnalyzeUsesDataRuleIDOverFingerprint(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "fingerprint-should-not-appear",
			Severity:    SeverityWarning,
			Title:       "High Error Rate",
			Data:        map[string]any{"rule_id": "rule-from-data"},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}

	task, ok := actions[0].Payload["task"].(string)
	if !ok {
		t.Fatalf("expected Payload[\"task\"] to be a string, got %T", actions[0].Payload["task"])
	}

	if !strings.Contains(task, "rule-from-data") {
		t.Errorf("Payload[\"task\"] should contain rule_id from Data[\"rule_id\"], got:\n%s", task)
	}
	if strings.Contains(task, "fingerprint-should-not-appear") {
		t.Errorf("Payload[\"task\"] should not contain fingerprint when Data[\"rule_id\"] is present, got:\n%s", task)
	}
}

func TestPatrolAgent_AnalyzeFallsBackToFingerprintWhenNoDataRuleID(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "fallback-fingerprint-id",
			Severity:    SeverityInfo,
			Title:       "Low Disk Space",
			Detail:      "disk usage above 80%",
			Data:        map[string]any{},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}

	task, ok := actions[0].Payload["task"].(string)
	if !ok {
		t.Fatalf("expected Payload[\"task\"] to be a string, got %T", actions[0].Payload["task"])
	}

	if !strings.Contains(task, "fallback-fingerprint-id") {
		t.Errorf("Payload[\"task\"] should fall back to Fingerprint when Data has no rule_id, got:\n%s", task)
	}
}

func TestPatrolAgent_AnalyzeFallsBackToFingerprintWhenDataIsNil(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "nil-data-fingerprint",
			Severity:    SeverityCritical,
			Title:       "Node NotReady",
			Data:        nil,
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}

	task, ok := actions[0].Payload["task"].(string)
	if !ok {
		t.Fatalf("expected Payload[\"task\"] to be a string, got %T", actions[0].Payload["task"])
	}

	if !strings.Contains(task, "nil-data-fingerprint") {
		t.Errorf("Payload[\"task\"] should fall back to Fingerprint when Data is nil, got:\n%s", task)
	}
}

func TestPatrolAgent_AnalyzePayloadPresentOnAllActions(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "fp-1",
			Severity:    SeverityCritical,
			Title:       "Alert One",
			Data:        map[string]any{"rule_id": "r1"},
		},
		{
			Fingerprint: "fp-2",
			Severity:    SeverityWarning,
			Title:       "Alert Two",
			Data:        map[string]any{},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}

	for i, action := range actions {
		if action.Payload == nil {
			t.Errorf("action[%d]: Payload is nil", i)
			continue
		}
		task, ok := action.Payload["task"].(string)
		if !ok {
			t.Errorf("action[%d]: Payload[\"task\"] is not a string, got %T", i, action.Payload["task"])
			continue
		}
		if task == "" {
			t.Errorf("action[%d]: Payload[\"task\"] is empty", i)
		}
	}
}

func TestPatrolAgent_CollectAggregatesFromCollector(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-10",
						Name:  "Test Alert",
						State: "firing",
						Labels: map[string]string{
							"severity": "critical",
						},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "")
	patrol := NewPatrolAgent(collector, nil, 1*time.Hour)

	findings, err := patrol.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
}

// TestPatrolAgent_CollectNilCollectorReturnsNil verifies the nil guard in
// Collect: when the collector is nil, Collect returns (nil, nil) without
// panicking.
func TestPatrolAgent_CollectNilCollectorReturnsNil(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings, err := patrol.Collect(context.Background())
	if err != nil {
		t.Fatalf("expected nil error with nil collector, got: %v", err)
	}
	if findings != nil {
		t.Errorf("expected nil findings with nil collector, got: %v", findings)
	}
}

// TestPatrolAgent_CollectPropagatesCollectorError verifies that when the
// underlying AlertCollector returns an error (e.g. the SigNoz API is down),
// Collect propagates that error to the caller.
func TestPatrolAgent_CollectPropagatesCollectorError(t *testing.T) {
	// Return a non-200 status to make the collector fail.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "")
	patrol := NewPatrolAgent(collector, nil, 1*time.Hour)

	_, err := patrol.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error from Collect when collector fails, got nil")
	}
}

// TestPatrolAgent_ExecuteNilEscalatorReturnsNil verifies the nil guard in
// Execute: when the escalator is nil, Execute returns nil without panicking.
func TestPatrolAgent_ExecuteNilEscalatorReturnsNil(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	actions := []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: Finding{Fingerprint: "fp-1", Title: "Some Alert"},
			Payload: map[string]any{"task": "investigate"},
		},
	}

	err := patrol.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("expected nil error with nil escalator, got: %v", err)
	}
}

// TestPatrolAgent_NameReturnsClusterPatrol verifies the Name() accessor.
func TestPatrolAgent_NameReturnsClusterPatrol(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)
	if patrol.Name() != "cluster-patrol" {
		t.Errorf("expected Name()=%q, got %q", "cluster-patrol", patrol.Name())
	}
}

// TestPatrolAgent_IntervalReturnsConfiguredValue verifies the Interval() accessor.
func TestPatrolAgent_IntervalReturnsConfiguredValue(t *testing.T) {
	want := 42 * time.Minute
	patrol := NewPatrolAgent(nil, nil, want)
	if patrol.Interval() != want {
		t.Errorf("expected Interval()=%v, got %v", want, patrol.Interval())
	}
}

// TestPatrolAgent_ExecuteDelegatesToEscalator verifies that when the escalator
// is non-nil, Execute delegates the actions to it, causing a POST to the
// orchestrator.
func TestPatrolAgent_ExecuteDelegatesToEscalator(t *testing.T) {
	var postReceived bool
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		postReceived = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-patrol"})
	}))
	defer orchestratorServer.Close()

	escalator := NewEscalator(NewOrchestratorClient(orchestratorServer.URL))
	patrol := NewPatrolAgent(nil, escalator, 1*time.Hour)

	actions := []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: Finding{Fingerprint: "fp-patrol-1", Title: "Pod OOMKilled"},
			Payload: map[string]any{"task": "investigate OOMKill"},
		},
	}

	err := patrol.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("Execute: unexpected error: %v", err)
	}
	if !postReceived {
		t.Error("expected Execute to delegate to escalator and POST to orchestrator")
	}
}

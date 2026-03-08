package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEscalator_SkipsWhenActiveJobExists(t *testing.T) {
	var jobSubmitted bool
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			// Return a matching job for the tag query.
			json.NewEncoder(w).Encode(orchestratorListResponse{
				Jobs:  []orchestratorJob{{ID: "existing-job", Status: "RUNNING"}},
				Total: 1,
			})
			return
		}
		jobSubmitted = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": "42"},
		},
	}}

	esc.Execute(context.Background(), actions)

	if jobSubmitted {
		t.Error("expected job NOT to be submitted when active job exists")
	}
}

func TestEscalator_SubmitsJobWhenNoActiveJob(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			// No matching jobs.
			json.NewEncoder(w).Encode(orchestratorListResponse{
				Jobs:  []orchestratorJob{},
				Total: 0,
			})
			return
		}
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": "42"},
		},
	}}

	esc.Execute(context.Background(), actions)

	if received == nil {
		t.Fatal("expected orchestrator job to be submitted")
	}
	source, ok := received["source"].(string)
	if !ok || source != "patrol:42" {
		t.Errorf("expected source patrol:42, got %v", received["source"])
	}
	tags, ok := received["tags"].([]any)
	if !ok || len(tags) != 1 || tags[0] != "alert:42" {
		t.Errorf("expected tags [alert:42], got %v", received["tags"])
	}
	// Patrol jobs should default to research profile.
	profile, ok := received["profile"].(string)
	if !ok || profile != "research" {
		t.Errorf("expected profile research, got %v", received["profile"])
	}
}

func TestEscalator_UsesPayloadTaskWhenPresent(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "improvement:test-coverage",
			Source:      "improvement:test-coverage",
			Title:       "New commits for test coverage review",
		},
		Payload: map[string]any{
			"task":    "Custom task prompt here",
			"profile": "code-fix",
		},
	}}

	esc.Execute(context.Background(), actions)

	if received == nil {
		t.Fatal("expected job to be submitted")
	}
	task, ok := received["task"].(string)
	if !ok || task != "Custom task prompt here" {
		t.Errorf("expected custom task, got %v", received["task"])
	}
	// Tag should be the fingerprint since no rule_id in Data.
	tags, ok := received["tags"].([]any)
	if !ok || len(tags) != 1 || tags[0] != "improvement:test-coverage" {
		t.Errorf("expected tag improvement:test-coverage, got %v", received["tags"])
	}
	// Source should be Finding.Source.
	source, ok := received["source"].(string)
	if !ok || source != "improvement:test-coverage" {
		t.Errorf("expected source improvement:test-coverage, got %v", received["source"])
	}
	// Profile should be passed through.
	profile, ok := received["profile"].(string)
	if !ok || profile != "code-fix" {
		t.Errorf("expected profile code-fix, got %v", received["profile"])
	}
}

func TestEscalator_ResubmitsAfterJobSucceeds(t *testing.T) {
	var jobSubmitted bool
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			// Verify the query only checks PENDING,RUNNING (not SUCCEEDED).
			status := r.URL.Query().Get("status")
			if status != "PENDING,RUNNING" {
				t.Errorf("expected status filter PENDING,RUNNING, got %q", status)
			}
			// No active jobs (previous job already succeeded).
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		jobSubmitted = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-2"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "improvement:test-coverage",
			Source:      "improvement:test-coverage",
			Title:       "New sweep after previous job completed",
		},
		Payload: map[string]any{
			"task":    "Re-run test coverage analysis",
			"profile": "code-fix",
		},
	}}

	esc.Execute(context.Background(), actions)

	if !jobSubmitted {
		t.Error("expected job to be resubmitted after previous job succeeded")
	}
}

func TestEscalator_LogActionSkipsDedup(t *testing.T) {
	esc := &Escalator{}

	actions := []Action{{
		Type: ActionLog,
		Finding: Finding{
			Fingerprint: "patrol.alert.99",
			Severity:    SeverityInfo,
			Title:       "info finding",
		},
	}}

	err := esc.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}
}

// TestEscalator_IncludesSHATagWhenLatestSHASet verifies that when the finding
// carries a "latest_sha" data field (set by gate-based agents) the escalator
// appends a "sha:<value>" tag to the job so that GitActivityGate can look up
// the processed commit on the next run.
func TestEscalator_IncludesSHATagWhenLatestSHASet(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "improvement:test-coverage",
			Source:      "improvement:test-coverage",
			Title:       "Test coverage job",
			Data: map[string]any{
				"commit_range": "abc123..def456",
				"latest_sha":   "def456",
			},
		},
		Payload: map[string]any{
			"task":    "Check test coverage",
			"profile": "code-fix",
		},
	}}

	esc.Execute(context.Background(), actions)

	if received == nil {
		t.Fatal("expected job to be submitted")
	}

	tags, ok := received["tags"].([]any)
	if !ok {
		t.Fatalf("expected tags array, got %T: %v", received["tags"], received["tags"])
	}

	foundFingerprint := false
	foundSHA := false
	for _, tag := range tags {
		s, _ := tag.(string)
		if s == "improvement:test-coverage" {
			foundFingerprint = true
		}
		if s == "sha:def456" {
			foundSHA = true
		}
	}
	if !foundFingerprint {
		t.Errorf("expected tag improvement:test-coverage in tags %v", tags)
	}
	if !foundSHA {
		t.Errorf("expected tag sha:def456 in tags %v (needed for GitActivityGate dedup)", tags)
	}
}

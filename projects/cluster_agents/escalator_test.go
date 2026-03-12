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

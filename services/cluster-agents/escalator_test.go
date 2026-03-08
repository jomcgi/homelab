package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEscalator_RoutesInfoToLog(t *testing.T) {
	store := NewMemFindingsStore()
	escalator := NewEscalator(store, nil, nil)

	actions := []Action{{
		Type: ActionLog,
		Finding: Finding{
			Fingerprint: "fp-1",
			Severity:    SeverityInfo,
			Title:       "test info",
		},
	}}

	err := escalator.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}
}

func TestEscalator_SubmitsOrchestratorJob(t *testing.T) {
	var received map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-123"})
	}))
	defer server.Close()

	store := NewMemFindingsStore()
	escalator := NewEscalator(store, nil, &OrchestratorClient{baseURL: server.URL, client: &http.Client{}})

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "fp-critical",
			Severity:    SeverityCritical,
			Title:       "Pod crash-looping",
			Detail:      "default/my-pod is crash-looping",
		},
	}}

	err := escalator.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}

	if received["task"] == nil || received["task"] == "" {
		t.Error("expected task to be set in orchestrator request")
	}
}

func TestEscalator_DeduplicatesFindings(t *testing.T) {
	store := NewMemFindingsStore()
	var callCount int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-123"})
	}))
	defer server.Close()

	escalator := NewEscalator(store, nil, &OrchestratorClient{baseURL: server.URL, client: &http.Client{}})

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "fp-dedup",
			Severity:    SeverityCritical,
			Title:       "same issue",
		},
	}}

	escalator.Execute(context.Background(), actions)
	escalator.Execute(context.Background(), actions)

	if callCount != 1 {
		t.Errorf("expected 1 orchestrator call (dedup), got %d", callCount)
	}
}

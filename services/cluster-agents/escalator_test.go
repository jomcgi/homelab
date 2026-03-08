package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEscalator_SkipsWhenOpenPRExists(t *testing.T) {
	var jobSubmitted bool
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		jobSubmitted = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{{Number: 99, State: "open"}})
	}))
	defer github.Close()

	esc := &Escalator{
		github:       NewGitHubPRChecker(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		mergeWindow:  0,
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": 42},
		},
	}}

	esc.Execute(context.Background(), actions)

	if jobSubmitted {
		t.Error("expected job NOT to be submitted when open PR exists")
	}
}

func TestEscalator_SubmitsJobWhenNoPR(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{})
	}))
	defer github.Close()

	esc := &Escalator{
		github:       NewGitHubPRChecker(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		mergeWindow:  0,
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": 42},
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

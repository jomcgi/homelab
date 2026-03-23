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

func TestReadmeFreshnessAgent_CollectWithActivity(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "abc123",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: add new service",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer githubServer.Close()

	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := orchestratorListResponse{
			Jobs:  []orchestratorJob{},
			Total: 0,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	gate := NewGitActivityGate(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient(orchestratorServer.URL),
		[]string{"ci-format-bot"},
		"main",
	)

	agent := NewReadmeFreshnessAgent(gate, nil, 1*time.Hour)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Source != "improvement:readme-freshness" {
		t.Errorf("expected source=improvement:readme-freshness, got %s", findings[0].Source)
	}
}

// TestReadmeFreshnessAgent_ExecuteDelegatesToEscalator verifies that
// ReadmeFreshnessAgent.Execute delegates to its Escalator.
func TestReadmeFreshnessAgent_ExecuteDelegatesToEscalator(t *testing.T) {
	var postReceived bool
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		postReceived = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-readme"})
	}))
	defer orchestratorServer.Close()

	escalator := NewEscalator(NewOrchestratorClient(orchestratorServer.URL))
	agent := NewReadmeFreshnessAgent(nil, escalator, time.Hour)

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: readmeFreshnessTag,
			Source:      readmeFreshnessTag,
			Title:       "README freshness check",
		},
		Payload: map[string]any{"task": "Audit README files for accuracy"},
	}}

	err := agent.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("Execute: unexpected error: %v", err)
	}
	if !postReceived {
		t.Error("expected Execute to delegate to escalator and POST to orchestrator")
	}
}

func TestReadmeFreshnessAgent_CollectNoActivity(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "bot111",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "ci-format-bot", Date: time.Now()},
					Message: "style: auto-format",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer githubServer.Close()

	gate := NewGitActivityGate(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient("http://should-not-be-called"),
		[]string{"ci-format-bot"},
		"main",
	)

	agent := NewReadmeFreshnessAgent(gate, nil, 1*time.Hour)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

// TestReadmeFreshnessAgent_CollectGateError verifies that Collect propagates
// errors returned by the gate (e.g. GitHub API unavailable).
func TestReadmeFreshnessAgent_CollectGateError(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer githubServer.Close()

	gate := NewGitActivityGate(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient("http://should-not-be-called"),
		[]string{"ci-format-bot"},
		"main",
	)

	agent := NewReadmeFreshnessAgent(gate, nil, 1*time.Hour)

	_, err := agent.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error from Collect when gate fails, got nil")
	}
	if !strings.Contains(err.Error(), "git activity check") {
		t.Errorf("expected error to contain 'git activity check', got: %v", err)
	}
}

func TestReadmeFreshnessAgent_AnalyzeCreatesJob(t *testing.T) {
	agent := NewReadmeFreshnessAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: readmeFreshnessTag,
			Source:      readmeFreshnessTag,
			Severity:    SeverityInfo,
			Title:       "README freshness check",
			Data: map[string]any{
				"commit_range": "abc123..def456",
			},
			Timestamp: time.Now(),
		},
	}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}
	if actions[0].Type != ActionOrchestratorJob {
		t.Errorf("expected action type=%s, got %s", ActionOrchestratorJob, actions[0].Type)
	}
	task, ok := actions[0].Payload["task"]
	if !ok {
		t.Fatal("expected payload to contain 'task' key")
	}
	taskStr, ok := task.(string)
	if !ok {
		t.Fatal("expected task to be a string")
	}
	if taskStr == "" {
		t.Error("expected non-empty task string")
	}
}

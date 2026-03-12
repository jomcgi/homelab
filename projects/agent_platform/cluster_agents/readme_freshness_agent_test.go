package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
	profile, ok := actions[0].Payload["profile"].(string)
	if !ok || profile != "code-fix" {
		t.Errorf("expected profile=code-fix, got %v", actions[0].Payload["profile"])
	}
}

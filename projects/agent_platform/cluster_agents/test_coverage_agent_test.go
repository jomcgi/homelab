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

func TestTestCoverageAgent_CollectWithActivity(t *testing.T) {
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

	agent := NewTestCoverageAgent(gate, nil, 1*time.Hour)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Source != "improvement:test-coverage" {
		t.Errorf("expected source=improvement:test-coverage, got %s", findings[0].Source)
	}
	// latest_sha must be set so the escalator can store it as a sha: tag.
	latestSHA, ok := findings[0].Data["latest_sha"].(string)
	if !ok || latestSHA == "" {
		t.Errorf("expected findings[0].Data[latest_sha] to be set, got %v", findings[0].Data["latest_sha"])
	}
}

func TestTestCoverageAgent_CollectNoActivity(t *testing.T) {
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

	agent := NewTestCoverageAgent(gate, nil, 1*time.Hour)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

func TestTestCoverageAgent_AnalyzeCreatesJob(t *testing.T) {
	agent := NewTestCoverageAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: testCoverageTag,
			Source:      testCoverageTag,
			Severity:    SeverityInfo,
			Title:       "Test coverage improvement opportunity",
			Data: map[string]any{
				"commit_range": "abc123..def456",
				"latest_sha":   "def456",
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
	// The task must include the commit range, not a ULID.
	if !strings.Contains(taskStr, "abc123..def456") {
		t.Errorf("expected task to contain commit range abc123..def456, got: %s", taskStr)
	}
}

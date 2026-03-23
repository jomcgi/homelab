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

// TestTestCoverageAgent_ExecuteDelegatesToEscalator verifies that
// TestCoverageAgent.Execute delegates directly to its Escalator, submitting
// the action to the orchestrator.
func TestTestCoverageAgent_ExecuteDelegatesToEscalator(t *testing.T) {
	var postReceived bool
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		postReceived = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-tc"})
	}))
	defer orchestratorServer.Close()

	escalator := NewEscalator(NewOrchestratorClient(orchestratorServer.URL))
	agent := NewTestCoverageAgent(nil, escalator, time.Hour)

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: testCoverageTag,
			Source:      testCoverageTag,
			Title:       "Test coverage job",
		},
		Payload: map[string]any{"task": "Run test coverage analysis"},
	}}

	err := agent.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("Execute: unexpected error: %v", err)
	}
	if !postReceived {
		t.Error("expected Execute to delegate to escalator and POST to orchestrator")
	}
}

// TestTestCoverageAgent_CollectGateError verifies that Collect returns an error
// wrapping "git activity check" when the GitHub API returns a non-200 status.
func TestTestCoverageAgent_CollectGateError(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer githubServer.Close()

	gate := NewGitActivityGate(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient("http://should-not-be-called"),
		[]string{"ci-format-bot"},
		"main",
	)

	agent := NewTestCoverageAgent(gate, nil, 1*time.Hour)

	_, err := agent.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "git activity check") {
		t.Errorf("expected error to contain 'git activity check', got: %v", err)
	}
}

// TestTestCoverageAgent_AnalyzeEmptyFindings verifies that Analyze returns nil
// actions when given an empty findings slice, not an empty non-nil slice.
func TestTestCoverageAgent_AnalyzeEmptyFindings(t *testing.T) {
	agent := NewTestCoverageAgent(nil, nil, time.Hour)

	actions, err := agent.Analyze(context.Background(), []Finding{})
	if err != nil {
		t.Fatalf("Analyze: unexpected error: %v", err)
	}
	if actions != nil {
		t.Errorf("expected nil actions for empty findings, got %v", actions)
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

// TestTestCoverageAgent_NameAndInterval verifies the Name() and Interval()
// accessors return the configured values.
func TestTestCoverageAgent_NameAndInterval(t *testing.T) {
	want := 25 * time.Minute
	agent := NewTestCoverageAgent(nil, nil, want)

	if agent.Name() != "test-coverage" {
		t.Errorf("expected Name()=%q, got %q", "test-coverage", agent.Name())
	}
	if agent.Interval() != want {
		t.Errorf("expected Interval()=%v, got %v", want, agent.Interval())
	}
}

// TestTestCoverageAgent_AnalyzeMissingCommitRangeFallsBackToEmpty verifies
// that when the finding's Data map has no "commit_range" key, Analyze still
// produces a valid non-empty task string and does not panic. The commit range
// appears as an empty parenthetical in the task.
func TestTestCoverageAgent_AnalyzeMissingCommitRangeFallsBackToEmpty(t *testing.T) {
	agent := NewTestCoverageAgent(nil, nil, time.Hour)

	findings := []Finding{
		{
			Fingerprint: testCoverageTag,
			Source:      testCoverageTag,
			Severity:    SeverityInfo,
			Title:       "Test coverage improvement opportunity",
			Data:        map[string]any{}, // no commit_range
			Timestamp:   time.Now(),
		},
	}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatalf("Analyze: unexpected error: %v", err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}

	task, ok := actions[0].Payload["task"].(string)
	if !ok {
		t.Fatalf("expected Payload[\"task\"] to be a string")
	}
	if task == "" {
		t.Error("expected non-empty task even with missing commit_range")
	}
	// The empty commit range produces an empty parenthetical "()" in the task.
	if !strings.Contains(task, "()") {
		t.Errorf("expected task to contain empty parenthetical when commit_range is missing, got:\n%s", task)
	}
}

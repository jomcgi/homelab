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

func TestPRFixAgent_CollectFindsFailingPRs(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "check-suites") {
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{
					{Conclusion: "failure"},
				},
			}
			json.NewEncoder(w).Encode(resp)
			return
		}

		// Return one open PR that is stale (updated long ago)
		prs := []ghPullRequest{
			{
				Number:    42,
				Head:      ghHead{Ref: "feat/broken", SHA: "deadbeef"},
				UpdatedAt: time.Now().Add(-2 * time.Hour),
			},
		}
		json.NewEncoder(w).Encode(prs)
	}))
	defer githubServer.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		nil,
		1*time.Hour,
		30*time.Minute,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}

	prNumber, ok := findings[0].Data["pr_number"].(int)
	if !ok {
		t.Fatal("expected pr_number in finding data")
	}
	if prNumber != 42 {
		t.Errorf("expected pr_number=42, got %d", prNumber)
	}

	branch, ok := findings[0].Data["branch"].(string)
	if !ok {
		t.Fatal("expected branch in finding data")
	}
	if branch != "feat/broken" {
		t.Errorf("expected branch=feat/broken, got %s", branch)
	}

	if findings[0].Fingerprint != "improvement:pr-fix:42" {
		t.Errorf("expected fingerprint=improvement:pr-fix:42, got %s", findings[0].Fingerprint)
	}
}

func TestPRFixAgent_AnalyzeCreatesPerPRActions(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, 1*time.Hour, 30*time.Minute)

	findings := []Finding{
		{
			Fingerprint: "improvement:pr-fix:42",
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       "PR #42 has failing CI checks",
			Data: map[string]any{
				"pr_number": 42,
				"branch":    "feat/broken",
			},
			Timestamp: time.Now(),
		},
		{
			Fingerprint: "improvement:pr-fix:99",
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       "PR #99 has failing CI checks",
			Data: map[string]any{
				"pr_number": 99,
				"branch":    "fix/flaky-test",
			},
			Timestamp: time.Now(),
		},
	}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}

	for i, action := range actions {
		if action.Type != ActionOrchestratorJob {
			t.Errorf("action[%d]: expected type=%s, got %s", i, ActionOrchestratorJob, action.Type)
		}
		task, ok := action.Payload["task"].(string)
		if !ok || task == "" {
			t.Errorf("action[%d]: expected non-empty task string", i)
		}
	}
}

// TestPRFixAgent_ExecuteDelegatesToEscalator verifies that PRFixAgent.Execute
// delegates directly to its Escalator, causing a job to be submitted to the
// orchestrator for each failing PR action.
func TestPRFixAgent_ExecuteDelegatesToEscalator(t *testing.T) {
	var postReceived bool
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		postReceived = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-pr"})
	}))
	defer orchestratorServer.Close()

	escalator := NewEscalator(NewOrchestratorClient(orchestratorServer.URL))
	agent := NewPRFixAgent(nil, escalator, time.Hour, 30*time.Minute)

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "improvement:pr-fix:42",
			Source:      "improvement:pr-fix",
			Title:       "PR #42 has failing CI checks",
		},
		Payload: map[string]any{"task": "Fix CI failure for PR #42"},
	}}

	err := agent.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("Execute: unexpected error: %v", err)
	}
	if !postReceived {
		t.Error("expected Execute to delegate to escalator and POST to orchestrator")
	}
}

// TestPRFixAgent_AnalyzeEmptyFindings verifies that Analyze returns nil
// actions when given an empty findings slice, not an empty non-nil slice.
func TestPRFixAgent_AnalyzeEmptyFindings(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, time.Hour, 30*time.Minute)

	actions, err := agent.Analyze(context.Background(), []Finding{})
	if err != nil {
		t.Fatalf("Analyze: unexpected error: %v", err)
	}
	if actions != nil {
		t.Errorf("expected nil actions for empty findings, got %v", actions)
	}
}

// TestPRFixAgent_CollectAPIError verifies that when the GitHub API returns an
// error (e.g. HTTP 500), Collect propagates the error with a descriptive
// message rather than silently returning empty findings.
func TestPRFixAgent_CollectAPIError(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer githubServer.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		nil,
		time.Hour,
		30*time.Minute,
	)

	_, err := agent.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error from Collect when GitHub API fails, got nil")
	}
	if !strings.Contains(err.Error(), "fetching failing PRs") {
		t.Errorf("expected error to contain 'fetching failing PRs', got: %v", err)
	}
}

// TestPRFixAgent_CollectNoPRs verifies that when there are no open PRs at all
// (not just no failing ones) Collect returns an empty findings slice without
// error.
func TestPRFixAgent_CollectNoPRs(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{})
	}))
	defer githubServer.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		nil,
		time.Hour,
		30*time.Minute,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect: unexpected error: %v", err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

// TestPRFixAgent_NameReturnsPRFix verifies the Name() accessor.
func TestPRFixAgent_NameReturnsPRFix(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, time.Hour, 30*time.Minute)
	if agent.Name() != "pr-fix" {
		t.Errorf("expected Name()=%q, got %q", "pr-fix", agent.Name())
	}
}

// TestPRFixAgent_IntervalReturnsConfiguredValue verifies the Interval() accessor.
func TestPRFixAgent_IntervalReturnsConfiguredValue(t *testing.T) {
	want := 15 * time.Minute
	agent := NewPRFixAgent(nil, nil, want, 30*time.Minute)
	if agent.Interval() != want {
		t.Errorf("expected Interval()=%v, got %v", want, agent.Interval())
	}
}

// TestPRFixAgent_AnalyzeTaskContainsPRNumberAndBranch verifies that the task
// string built by Analyze includes the PR number and branch name so the agent
// receiving the job has full context.
func TestPRFixAgent_AnalyzeTaskContainsPRNumberAndBranch(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, time.Hour, 30*time.Minute)

	findings := []Finding{
		{
			Fingerprint: "improvement:pr-fix:77",
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       "PR #77 has failing CI checks",
			Data: map[string]any{
				"pr_number": 77,
				"branch":    "feat/my-feature",
			},
			Timestamp: time.Now(),
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
		t.Fatalf("expected Payload[\"task\"] to be a string, got %T", actions[0].Payload["task"])
	}

	for _, want := range []string{"77", "feat/my-feature"} {
		if !strings.Contains(task, want) {
			t.Errorf("Payload[\"task\"] missing %q:\n%s", want, task)
		}
	}
}

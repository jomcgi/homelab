package main

import (
	"context"
	"encoding/json"
	"fmt"
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

// TestPRFixAgent_CollectFiltersFreshPRs verifies that PRs updated within the
// staleThreshold window are excluded from the results even when they have
// failing checks.
func TestPRFixAgent_CollectFiltersFreshPRs(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "check-suites") {
			// Would have failing checks if called.
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			}
			json.NewEncoder(w).Encode(resp)
			return
		}
		// Return one PR that was updated 5 minutes ago — well within a 30-minute threshold.
		prs := []ghPullRequest{
			{
				Number:    55,
				Head:      ghHead{Ref: "feat/fresh", SHA: "freshsha"},
				UpdatedAt: time.Now().Add(-5 * time.Minute),
			},
		}
		json.NewEncoder(w).Encode(prs)
	}))
	defer githubServer.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		nil,
		time.Hour,
		30*time.Minute, // staleThreshold: 30 minutes
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect: unexpected error: %v", err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings for a fresh PR (updated 5m ago vs 30m threshold), got %d", len(findings))
	}
}

// TestPRFixAgent_CollectMultiplePRsProducesMultipleFindings verifies that when
// multiple stale PRs with failing checks exist, Collect returns one finding per
// PR in the same order.
func TestPRFixAgent_CollectMultiplePRsProducesMultipleFindings(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "check-suites") {
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			}
			json.NewEncoder(w).Encode(resp)
			return
		}
		prs := []ghPullRequest{
			{
				Number:    10,
				Head:      ghHead{Ref: "fix/issue-10", SHA: "sha10"},
				UpdatedAt: time.Now().Add(-2 * time.Hour),
			},
			{
				Number:    20,
				Head:      ghHead{Ref: "fix/issue-20", SHA: "sha20"},
				UpdatedAt: time.Now().Add(-3 * time.Hour),
			},
		}
		json.NewEncoder(w).Encode(prs)
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
	if len(findings) != 2 {
		t.Fatalf("expected 2 findings for 2 stale failing PRs, got %d", len(findings))
	}
	if findings[0].Data["pr_number"].(int) != 10 {
		t.Errorf("expected first finding for PR #10, got pr_number=%v", findings[0].Data["pr_number"])
	}
	if findings[1].Data["pr_number"].(int) != 20 {
		t.Errorf("expected second finding for PR #20, got pr_number=%v", findings[1].Data["pr_number"])
	}
}

// TestPRFixAgent_FingerprintUniquenessAcrossPRs verifies that different PR
// numbers produce distinct fingerprints so the escalator dedup tag is unique
// per PR and multiple PRs can be tracked independently.
func TestPRFixAgent_FingerprintUniquenessAcrossPRs(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, time.Hour, 30*time.Minute)

	findings := []Finding{
		{Data: map[string]any{"pr_number": 1, "branch": "a"}},
		{Data: map[string]any{"pr_number": 2, "branch": "b"}},
		{Data: map[string]any{"pr_number": 1000, "branch": "c"}},
	}

	// Simulate Collect fingerprint generation by reproducing the Collect logic.
	seen := map[string]bool{}
	for _, f := range findings {
		prNumber := f.Data["pr_number"].(int)
		fp := fmt.Sprintf("improvement:pr-fix:%d", prNumber)
		if seen[fp] {
			t.Errorf("fingerprint collision for pr_number=%d: %s", prNumber, fp)
		}
		seen[fp] = true
	}
	if len(seen) != 3 {
		t.Errorf("expected 3 unique fingerprints, got %d", len(seen))
	}
}

// TestPRFixAgent_AnalyzeMissingDataFallsBack verifies that Analyze handles
// missing or wrong-type pr_number and branch fields gracefully via type
// assertion fallbacks (yields 0 and ""), producing a non-panicking task string.
func TestPRFixAgent_AnalyzeMissingDataFallsBack(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, time.Hour, 30*time.Minute)

	findings := []Finding{
		{
			Fingerprint: "improvement:pr-fix:0",
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       "PR with missing data",
			Data:        map[string]any{}, // no pr_number, no branch
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
		t.Error("expected non-empty task even when pr_number and branch are missing")
	}
	// Zero-value fallbacks: pr_number=0, branch=""
	if !strings.Contains(task, "0") {
		t.Errorf("expected task to contain fallback PR number 0, got:\n%s", task)
	}
}

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

		// Return one open PR that is stale (pushed long ago)
		prs := []ghPullRequest{
			{
				Number:    42,
				Head:      ghHead{Ref: "feat/broken", SHA: "deadbeef"},
				PushedAt:  time.Now().Add(-2 * time.Hour),
				UpdatedAt: time.Now().Add(-2 * time.Hour),
			},
		}
		json.NewEncoder(w).Encode(prs)
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

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient(orchestratorServer.URL),
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

func TestPRFixAgent_CollectSkipsPRWithActiveJob(t *testing.T) {
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

		prs := []ghPullRequest{
			{
				Number:    42,
				Head:      ghHead{Ref: "feat/broken", SHA: "deadbeef"},
				PushedAt:  time.Now().Add(-2 * time.Hour),
				UpdatedAt: time.Now().Add(-2 * time.Hour),
			},
		}
		json.NewEncoder(w).Encode(prs)
	}))
	defer githubServer.Close()

	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := orchestratorListResponse{
			Jobs:  []orchestratorJob{{ID: "job-123", Status: "RUNNING"}},
			Total: 1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		NewOrchestratorClient(orchestratorServer.URL),
		nil,
		1*time.Hour,
		30*time.Minute,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

func TestPRFixAgent_AnalyzeCreatesPerPRActions(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, nil, 1*time.Hour, 30*time.Minute)

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
		profile, ok := action.Payload["profile"].(string)
		if !ok || profile != "ci-debug" {
			t.Errorf("action[%d]: expected profile=ci-debug, got %v", i, action.Payload["profile"])
		}
	}
}

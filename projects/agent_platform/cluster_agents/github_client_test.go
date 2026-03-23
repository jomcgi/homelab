package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGitHubClient_LatestNonBotCommit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/repos/jomcgi/homelab/commits" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("sha") != "main" {
			t.Errorf("expected sha=main, got %s", r.URL.Query().Get("sha"))
		}
		if r.URL.Query().Get("per_page") != "20" {
			t.Errorf("expected per_page=20, got %s", r.URL.Query().Get("per_page"))
		}
		if r.Header.Get("Accept") != "application/vnd.github+json" {
			t.Errorf("unexpected Accept header: %s", r.Header.Get("Accept"))
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("expected auth header 'Bearer test-token', got %q", r.Header.Get("Authorization"))
		}

		commits := []ghCommit{
			{
				SHA: "abc123",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "ci-format-bot", Date: time.Now()},
					Message: "style: auto-format",
				},
			},
			{
				SHA: "def456",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: add new service",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	commit, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-format-bot"})
	if err != nil {
		t.Fatal(err)
	}
	if commit == nil {
		t.Fatal("expected a commit, got nil")
	}
	if commit.SHA != "def456" {
		t.Errorf("expected SHA def456, got %s", commit.SHA)
	}
	if commit.Commit.Author.Name != "jomcgi" {
		t.Errorf("expected author jomcgi, got %s", commit.Commit.Author.Name)
	}
	if commit.Commit.Message != "feat: add new service" {
		t.Errorf("expected message 'feat: add new service', got %s", commit.Commit.Message)
	}
}

func TestGitHubClient_LatestNonBotCommit_AllBots(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "aaa111",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "ci-format-bot", Date: time.Now()},
					Message: "style: auto-format",
				},
			},
			{
				SHA: "bbb222",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "dependabot", Date: time.Now()},
					Message: "chore: bump deps",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	commit, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-format-bot", "dependabot"})
	if err != nil {
		t.Fatal(err)
	}
	if commit != nil {
		t.Errorf("expected nil commit when all authors are bots, got SHA %s", commit.SHA)
	}
}

func TestGitHubClient_LatestNonBotCommit_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	_, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-format-bot"})
	if err == nil {
		t.Fatal("expected error on 500 response")
	}
}

func TestGitHubClient_OpenPRsWithFailingChecks(t *testing.T) {
	now := time.Now()
	staleUpdatedAt := now.Add(-2 * time.Hour)
	freshUpdatedAt := now.Add(-10 * time.Minute)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:    42,
					Head:      ghHead{Ref: "fix/stale-branch", SHA: "sha42"},
					UpdatedAt: staleUpdatedAt,
				},
				{
					Number:    43,
					Head:      ghHead{Ref: "feat/fresh-branch", SHA: "sha43"},
					UpdatedAt: freshUpdatedAt,
				},
			}
			json.NewEncoder(w).Encode(prs)
		case "/repos/jomcgi/homelab/commits/sha42/check-suites":
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			}
			json.NewEncoder(w).Encode(resp)
		case "/repos/jomcgi/homelab/commits/sha43/check-suites":
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			}
			json.NewEncoder(w).Encode(resp)
		default:
			t.Errorf("unexpected path: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(prs) != 1 {
		t.Fatalf("expected 1 PR, got %d", len(prs))
	}
	if prs[0].Number != 42 {
		t.Errorf("expected PR #42, got #%d", prs[0].Number)
	}
}

func TestGitHubClient_OpenPRsWithFailingChecks_AllPassing(t *testing.T) {
	now := time.Now()
	staleUpdatedAt := now.Add(-2 * time.Hour)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:    42,
					Head:      ghHead{Ref: "fix/stale-branch", SHA: "sha42"},
					UpdatedAt: staleUpdatedAt,
				},
			}
			json.NewEncoder(w).Encode(prs)
		case "/repos/jomcgi/homelab/commits/sha42/check-suites":
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "success"}},
			}
			json.NewEncoder(w).Encode(resp)
		default:
			t.Errorf("unexpected path: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(prs) != 0 {
		t.Errorf("expected 0 PRs, got %d", len(prs))
	}
}

// TestGitHubClient_OpenPRsWithFailingChecks_APIError verifies that a non-200
// response from the /pulls endpoint is propagated as an error rather than
// silently returning an empty list.
func TestGitHubClient_OpenPRsWithFailingChecks_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	_, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err == nil {
		t.Fatal("expected error on 500 response from /pulls")
	}
}

// TestGitHubClient_OpenPRsWithFailingChecks_SkipsPRWithCheckError verifies
// that when the check-suites request for a specific PR fails, that PR is
// skipped (logged as a warning) rather than causing the whole call to fail.
// Other PRs that have failing checks are still returned.
func TestGitHubClient_OpenPRsWithFailingChecks_SkipsPRWithCheckError(t *testing.T) {
	now := time.Now()
	staleUpdatedAt := now.Add(-2 * time.Hour)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					// PR where check-suites will error — should be skipped.
					Number:    10,
					Head:      ghHead{Ref: "feat/unstable", SHA: "sha10"},
					UpdatedAt: staleUpdatedAt,
				},
				{
					// PR where check-suites will report failure — should be included.
					Number:    11,
					Head:      ghHead{Ref: "fix/real-failure", SHA: "sha11"},
					UpdatedAt: staleUpdatedAt,
				},
			}
			json.NewEncoder(w).Encode(prs)
		case "/repos/jomcgi/homelab/commits/sha10/check-suites":
			// Simulate a server error for this PR's checks.
			w.WriteHeader(http.StatusInternalServerError)
		case "/repos/jomcgi/homelab/commits/sha11/check-suites":
			resp := ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			}
			json.NewEncoder(w).Encode(resp)
		default:
			t.Errorf("unexpected path: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatalf("expected no error (PR with bad checks is skipped), got: %v", err)
	}
	// Only PR #11 should appear — PR #10 was skipped due to check-suites error.
	if len(prs) != 1 {
		t.Fatalf("expected 1 PR, got %d", len(prs))
	}
	if prs[0].Number != 11 {
		t.Errorf("expected PR #11, got #%d", prs[0].Number)
	}
}

// TestGitHubClient_OpenPRsWithFailingChecks_EmptyList verifies that when the
// API returns an empty pull-request list the result is an empty (non-nil)
// slice without error.
func TestGitHubClient_OpenPRsWithFailingChecks_EmptyList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{})
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(prs) != 0 {
		t.Errorf("expected 0 PRs, got %d", len(prs))
	}
}

// TestGitHubClient_hasFailingChecks_AllPass verifies that when all check
// suites have "success" conclusion the function returns false.
func TestGitHubClient_hasFailingChecks_AllPass(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ghCheckSuitesResponse{
			CheckSuites: []ghCheckSuite{
				{Conclusion: "success"},
				{Conclusion: "neutral"},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	hasFailing, err := client.hasFailingChecks(context.Background(), "sha-abc")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if hasFailing {
		t.Error("expected hasFailing=false when all checks pass")
	}
}

// TestGitHubClient_hasFailingChecks_NoSuites verifies that an empty
// check-suites list is treated as no failures.
func TestGitHubClient_hasFailingChecks_NoSuites(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ghCheckSuitesResponse{CheckSuites: []ghCheckSuite{}}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	hasFailing, err := client.hasFailingChecks(context.Background(), "sha-xyz")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if hasFailing {
		t.Error("expected hasFailing=false when check-suites list is empty")
	}
}

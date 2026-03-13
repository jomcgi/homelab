package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGitActivityGate_NewCommits(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/jobs" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("status") != "SUCCEEDED" {
			t.Errorf("expected status=SUCCEEDED, got %s", r.URL.Query().Get("status"))
		}
		if r.URL.Query().Get("tags") != "ci:main" {
			t.Errorf("expected tags=ci:main, got %s", r.URL.Query().Get("tags"))
		}
		resp := orchestratorListResponse{
			Jobs: []orchestratorJob{
				{ID: "job-1", Status: "SUCCEEDED", CommitSHA: "old123"},
			},
			Total: 1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "new456",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: something new",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer githubServer.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		orchestrator: NewOrchestratorClient(orchestratorServer.URL),
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected hasActivity=true")
	}
	if commitRange != "old123..new456" {
		t.Errorf("expected commitRange=old123..new456, got %s", commitRange)
	}
}

func TestGitActivityGate_NoNewCommits(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "bot111",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "ci-format-bot", Date: time.Now()},
					Message: "style: auto-format",
				},
			},
			{
				SHA: "bot222",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "dependabot", Date: time.Now()},
					Message: "chore: bump deps",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer githubServer.Close()

	// Orchestrator shouldn't even be called when all commits are bots.
	gate := &GitActivityGate{
		github:       NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		orchestrator: NewOrchestratorClient("http://should-not-be-called"),
		botAuthors:   []string{"ci-format-bot", "dependabot"},
		branch:       "main",
	}

	commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if hasActivity {
		t.Error("expected hasActivity=false when all commits are bots")
	}
	if commitRange != "" {
		t.Errorf("expected empty commitRange, got %s", commitRange)
	}
}

func TestGitActivityGate_FirstRun_NoExistingJob(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := orchestratorListResponse{
			Jobs:  []orchestratorJob{},
			Total: 0,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "first123",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: initial commit",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer githubServer.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		orchestrator: NewOrchestratorClient(orchestratorServer.URL),
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected hasActivity=true on first run")
	}
	if commitRange != "first123" {
		t.Errorf("expected commitRange=first123, got %s", commitRange)
	}
}

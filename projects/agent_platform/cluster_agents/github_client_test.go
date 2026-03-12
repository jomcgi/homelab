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

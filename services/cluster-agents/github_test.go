package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGitHubPRChecker_OpenPRExists(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if q.Get("state") != "open" {
			t.Errorf("expected state=open, got %s", q.Get("state"))
		}
		if q.Get("labels") != "alert:42" {
			t.Errorf("expected labels=alert:42, got %s", q.Get("labels"))
		}
		json.NewEncoder(w).Encode([]ghPullRequest{{Number: 99, State: "open"}})
	}))
	defer server.Close()

	checker := NewGitHubPRChecker(server.URL, "test-token", "jomcgi/homelab")
	exists, err := checker.HasOpenPR(context.Background(), "42")
	if err != nil {
		t.Fatal(err)
	}
	if !exists {
		t.Error("expected open PR to exist")
	}
}

func TestGitHubPRChecker_NoOpenPR(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{})
	}))
	defer server.Close()

	checker := NewGitHubPRChecker(server.URL, "test-token", "jomcgi/homelab")
	exists, err := checker.HasOpenPR(context.Background(), "42")
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Error("expected no open PR")
	}
}

func TestGitHubPRChecker_RecentlyMerged(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if q.Get("state") == "open" {
			json.NewEncoder(w).Encode([]ghPullRequest{})
			return
		}
		now := time.Now()
		json.NewEncoder(w).Encode([]ghPullRequest{{
			Number:   100,
			State:    "closed",
			MergedAt: &now,
		}})
	}))
	defer server.Close()

	checker := NewGitHubPRChecker(server.URL, "test-token", "jomcgi/homelab")
	merged, err := checker.HasRecentlyMergedPR(context.Background(), "42", 1*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if !merged {
		t.Error("expected recently merged PR")
	}
}

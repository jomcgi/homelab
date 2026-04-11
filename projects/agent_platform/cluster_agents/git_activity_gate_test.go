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
				{ID: "job-1", Status: "SUCCEEDED", Tags: []string{"ci:main", "sha:old123"}},
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

	latestSHA, commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected hasActivity=true")
	}
	if latestSHA != "new456" {
		t.Errorf("expected latestSHA=new456, got %s", latestSHA)
	}
	// commitRange must use the git SHA from the sha: tag, not the job ID.
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

	latestSHA, commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if hasActivity {
		t.Error("expected hasActivity=false when all commits are bots")
	}
	if latestSHA != "" {
		t.Errorf("expected empty latestSHA, got %s", latestSHA)
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

	latestSHA, commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected hasActivity=true on first run")
	}
	if latestSHA != "first123" {
		t.Errorf("expected latestSHA=first123, got %s", latestSHA)
	}
	// On first run, commitRange is just the SHA (no "from" part).
	if commitRange != "first123" {
		t.Errorf("expected commitRange=first123, got %s", commitRange)
	}
}

func TestGitActivityGate_AlreadyProcessed(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := orchestratorListResponse{
			Jobs: []orchestratorJob{
				{ID: "job-1", Status: "SUCCEEDED", Tags: []string{"ci:main", "sha:abc123"}},
			},
			Total: 1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "abc123", // same SHA as last processed
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: already processed",
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

	latestSHA, commitRange, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err != nil {
		t.Fatal(err)
	}
	if hasActivity {
		t.Error("expected hasActivity=false when latest commit was already processed")
	}
	if latestSHA != "" || commitRange != "" {
		t.Errorf("expected empty latestSHA and commitRange, got %q, %q", latestSHA, commitRange)
	}
}

// TestGitActivityGate_JobWithoutSHATag_TreatedAsFirstRun verifies that jobs
// submitted before the sha: tag feature was introduced (which have no sha: tag
// and whose ID is a ULID, not a git hash) result in first-run behaviour rather
// than an invalid "ULID..gitSHA" commit range.
func TestGitActivityGate_JobWithoutSHATag_TreatedAsFirstRun(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := orchestratorListResponse{
			Jobs: []orchestratorJob{
				// Old-format job: ULID ID, no sha: tag.
				{ID: "01KKJ0HZDBCTZ169JTHXHXJ3GM", Status: "SUCCEEDED", Tags: []string{"improvement:test-coverage"}},
			},
			Total: 1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "5ef12dd3",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "test: add coverage",
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

	latestSHA, commitRange, hasActivity, err := gate.Check(context.Background(), "improvement:test-coverage")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected hasActivity=true when job has no sha: tag")
	}
	if latestSHA != "5ef12dd3" {
		t.Errorf("expected latestSHA=5ef12dd3, got %s", latestSHA)
	}
	// Without a prior sha: tag, range is just the latest SHA — never a
	// "ULID..gitSHA" which would be an invalid git range.
	if commitRange != "5ef12dd3" {
		t.Errorf("expected commitRange=5ef12dd3 (first-run), got %s", commitRange)
	}
}

// TestGitActivityGate_GitHubAPIError verifies that when the GitHub commits
// endpoint returns a non-200 response, Check propagates the error with a
// "fetching latest commit" wrapper.
func TestGitActivityGate_GitHubAPIError(t *testing.T) {
	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer githubServer.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(githubServer.URL, "test-token", "jomcgi/homelab"),
		orchestrator: NewOrchestratorClient("http://should-not-be-called"),
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	_, _, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err == nil {
		t.Fatal("expected error when GitHub API fails, got nil")
	}
	if hasActivity {
		t.Error("expected hasActivity=false on error")
	}
	errStr := err.Error()
	if len(errStr) == 0 || errStr[:len("fetching latest commit")] != "fetching latest commit" {
		t.Errorf("expected error to start with 'fetching latest commit', got: %v", err)
	}
}

// TestGitActivityGate_OrchestratorNon200 verifies that when the orchestrator
// returns a non-200 status from the jobs endpoint, lastProcessedCommit returns
// an error and Check wraps it with "fetching last processed commit".
func TestGitActivityGate_OrchestratorNon200(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "abc999",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "feat: something",
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

	_, _, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err == nil {
		t.Fatal("expected error when orchestrator returns non-200, got nil")
	}
	if hasActivity {
		t.Error("expected hasActivity=false on error")
	}
	errStr := err.Error()
	const wantPrefix = "fetching last processed commit"
	if len(errStr) < len(wantPrefix) || errStr[:len(wantPrefix)] != wantPrefix {
		t.Errorf("expected error to start with %q, got: %v", wantPrefix, err)
	}
}

// TestGitActivityGate_OrchestratorMalformedJSON verifies that when the
// orchestrator returns 200 OK with invalid JSON, lastProcessedCommit returns an
// error and Check wraps it with "fetching last processed commit".
func TestGitActivityGate_OrchestratorMalformedJSON(t *testing.T) {
	orchestratorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("not-valid-json{{{"))
	}))
	defer orchestratorServer.Close()

	githubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA: "def777",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: time.Now()},
					Message: "fix: another fix",
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

	_, _, hasActivity, err := gate.Check(context.Background(), "ci:main")
	if err == nil {
		t.Fatal("expected error when orchestrator returns malformed JSON, got nil")
	}
	if hasActivity {
		t.Error("expected hasActivity=false on error")
	}
	const wantPrefix = "fetching last processed commit"
	errStr := err.Error()
	if len(errStr) < len(wantPrefix) || errStr[:len(wantPrefix)] != wantPrefix {
		t.Errorf("expected error to start with %q, got: %v", wantPrefix, err)
	}
}

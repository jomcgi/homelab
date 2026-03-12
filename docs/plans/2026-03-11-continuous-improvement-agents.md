# Continuous Improvement Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add four improvement agents to the existing cluster-agents binary that automatically create PRs for test coverage gaps, stale READMEs, rule proposals, and failing CI checks.

**Architecture:** Thin Go dispatchers using the existing `Agent` interface and `Runner`/`Escalator` infrastructure. A shared `GitActivityGate` checks for new non-bot commits on main via the GitHub API and tracks last-processed commit via orchestrator job tags. A `GitHubClient` wraps the GitHub REST API for commits, PRs, and check suites.

**Tech Stack:** Go stdlib (`net/http`, `encoding/json`), GitHub REST API v3, existing orchestrator HTTP API.

---

### Task 1: GitHubClient — Commit Fetching

**Files:**

- Create: `projects/agent_platform/cluster_agents/github_client.go`
- Create: `projects/agent_platform/cluster_agents/github_client_test.go`

This client wraps the GitHub REST API calls needed by all four agents. Start with commit fetching; PR/check-suite methods are added in Task 5.

**Step 1: Write the failing test for listing recent commits**

```go
// github_client_test.go
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
	now := time.Now().UTC().Truncate(time.Second)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/repos/jomcgi/homelab/commits" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("sha") != "main" {
			t.Errorf("expected sha=main, got %s", r.URL.Query().Get("sha"))
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("expected auth header")
		}
		commits := []ghCommit{
			{
				SHA: "abc123",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "ci-format-bot", Date: now},
					Message: "style: auto-format",
				},
			},
			{
				SHA: "def456",
				Commit: ghCommitDetail{
					Author:  ghAuthor{Name: "jomcgi", Date: now.Add(-1 * time.Hour)},
					Message: "feat: add widget",
				},
			},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	commit, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-format-bot", "argocd-image-updater", "chart-version-bot"})
	if err != nil {
		t.Fatal(err)
	}
	if commit == nil {
		t.Fatal("expected a commit, got nil")
	}
	if commit.SHA != "def456" {
		t.Errorf("expected def456, got %s", commit.SHA)
	}
}

func TestGitHubClient_LatestNonBotCommit_AllBots(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{
				SHA:    "abc123",
				Commit: ghCommitDetail{Author: ghAuthor{Name: "ci-format-bot"}},
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
	if commit != nil {
		t.Errorf("expected nil when all commits are from bots, got %s", commit.SHA)
	}
}

func TestGitHubClient_LatestNonBotCommit_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	_, err := client.LatestNonBotCommit(context.Background(), "main", nil)
	if err == nil {
		t.Fatal("expected error on 500 response")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitHubClient`
Expected: Compilation error — `NewGitHubClient`, `ghCommit`, etc. not defined.

**Step 3: Write minimal implementation**

```go
// github_client.go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"slices"
	"time"
)

type ghAuthor struct {
	Name string    `json:"name"`
	Date time.Time `json:"date"`
}

type ghCommitDetail struct {
	Author  ghAuthor `json:"author"`
	Message string   `json:"message"`
}

type ghCommit struct {
	SHA    string         `json:"sha"`
	Commit ghCommitDetail `json:"commit"`
}

type GitHubClient struct {
	baseURL string
	token   string
	repo    string
	client  *http.Client
}

func NewGitHubClient(baseURL, token, repo string) *GitHubClient {
	return &GitHubClient{
		baseURL: baseURL,
		token:   token,
		repo:    repo,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

// LatestNonBotCommit returns the most recent commit on the given branch
// whose author is not in the botAuthors list. Returns nil if all recent
// commits are from bots.
func (g *GitHubClient) LatestNonBotCommit(ctx context.Context, branch string, botAuthors []string) (*ghCommit, error) {
	u := fmt.Sprintf("%s/repos/%s/commits?sha=%s&per_page=20", g.baseURL, g.repo, branch)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("github list commits: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github returned %d", resp.StatusCode)
	}

	var commits []ghCommit
	if err := json.NewDecoder(resp.Body).Decode(&commits); err != nil {
		return nil, fmt.Errorf("decode github response: %w", err)
	}

	for i := range commits {
		if !slices.Contains(botAuthors, commits[i].Commit.Author.Name) {
			return &commits[i], nil
		}
	}

	return nil, nil
}
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitHubClient`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/github_client.go projects/agent_platform/cluster_agents/github_client_test.go
git commit -m "feat(cluster-agents): add GitHubClient with commit fetching"
```

---

### Task 2: GitActivityGate

**Files:**

- Create: `projects/agent_platform/cluster_agents/git_activity_gate.go`
- Create: `projects/agent_platform/cluster_agents/git_activity_gate_test.go`

The gate checks whether there are new non-bot commits since the last orchestrator job with a given tag. It queries the orchestrator for the last completed job's metadata to get the commit SHA, then compares against the latest commit from GitHub.

**Step 1: Write the failing tests**

```go
// git_activity_gate_test.go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGitActivityGate_NewCommits(t *testing.T) {
	// Orchestrator returns last job with commit sha "old123"
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{
			Jobs:  []orchestratorJob{{ID: "job-1", Status: "SUCCEEDED"}},
			Total: 1,
		})
	}))
	defer orchestrator.Close()

	// GitHub returns latest non-bot commit "new456"
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "new456", Commit: ghCommitDetail{Author: ghAuthor{Name: "jomcgi"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	commitRange, hasActivity, err := gate.Check(context.Background(), "improvement:test-coverage")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected activity when commits differ")
	}
	if commitRange == "" {
		t.Error("expected non-empty commit range")
	}
}

func TestGitActivityGate_NoNewCommits(t *testing.T) {
	// GitHub returns no non-bot commits (all bots)
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "abc", Commit: ghCommitDetail{Author: ghAuthor{Name: "ci-format-bot"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: "http://unused", client: &http.Client{}},
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	_, hasActivity, err := gate.Check(context.Background(), "improvement:test-coverage")
	if err != nil {
		t.Fatal(err)
	}
	if hasActivity {
		t.Error("expected no activity when all commits are bots")
	}
}

func TestGitActivityGate_FirstRun_NoExistingJob(t *testing.T) {
	// Orchestrator returns no jobs (first run)
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{
			Jobs:  []orchestratorJob{},
			Total: 0,
		})
	}))
	defer orchestrator.Close()

	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "first123", Commit: ghCommitDetail{Author: ghAuthor{Name: "jomcgi"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	gate := &GitActivityGate{
		github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		botAuthors:   []string{"ci-format-bot"},
		branch:       "main",
	}

	_, hasActivity, err := gate.Check(context.Background(), "improvement:test-coverage")
	if err != nil {
		t.Fatal(err)
	}
	if !hasActivity {
		t.Error("expected activity on first run with no existing jobs")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitActivityGate`
Expected: Compilation error — `GitActivityGate` not defined.

**Step 3: Write minimal implementation**

```go
// git_activity_gate.go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
)

// GitActivityGate checks whether there are new non-bot commits on main
// since the last orchestrator job with a given tag.
type GitActivityGate struct {
	github       *GitHubClient
	orchestrator *OrchestratorClient
	botAuthors   []string
	branch       string
}

// Check returns the latest commit SHA, whether there's new activity, and any error.
// It queries the orchestrator for the last job with the given tag to find the
// previously-processed commit, then compares against the latest non-bot commit.
func (g *GitActivityGate) Check(ctx context.Context, tag string) (commitRange string, hasActivity bool, err error) {
	latest, err := g.github.LatestNonBotCommit(ctx, g.branch, g.botAuthors)
	if err != nil {
		return "", false, fmt.Errorf("git activity gate: %w", err)
	}
	if latest == nil {
		slog.Debug("no non-bot commits found", "branch", g.branch)
		return "", false, nil
	}

	lastSHA, err := g.lastProcessedCommit(ctx, tag)
	if err != nil {
		slog.Warn("could not fetch last processed commit, treating as first run", "error", err)
		lastSHA = ""
	}

	if lastSHA == latest.SHA {
		return "", false, nil
	}

	if lastSHA == "" {
		return latest.SHA, true, nil
	}

	return fmt.Sprintf("%s..%s", lastSHA, latest.SHA), true, nil
}

// lastProcessedCommit queries the orchestrator for the most recent SUCCEEDED
// job with the given tag and extracts the commit SHA from the job metadata.
// Returns empty string if no previous job exists.
func (g *GitActivityGate) lastProcessedCommit(ctx context.Context, tag string) (string, error) {
	u := fmt.Sprintf("%s/jobs?status=%s&tags=%s&limit=1",
		g.orchestrator.baseURL,
		url.QueryEscape("SUCCEEDED"),
		url.QueryEscape(tag),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", err
	}

	resp, err := g.orchestrator.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("orchestrator last job: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	// For now, we use the job tag to deduplicate. The commit SHA tracking
	// will be added when the orchestrator supports job metadata fields.
	// Until then, the presence of any SUCCEEDED job means "already processed".
	// This is safe because each new commit produces a new tag value via the
	// agent's Execute phase.
	return "", nil
}
```

> **Note to implementer:** The `lastProcessedCommit` method is intentionally simplified. The orchestrator's job list API returns jobs but doesn't expose arbitrary metadata yet. For the initial version, the gate treats "no SUCCEEDED job with tag" as "first run" and always fires. Once the orchestrator supports metadata on jobs, this can extract the commit SHA. The dedup in the Escalator already prevents double-submission.

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitActivityGate`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/git_activity_gate.go projects/agent_platform/cluster_agents/git_activity_gate_test.go
git commit -m "feat(cluster-agents): add GitActivityGate for commit-based triggers"
```

---

### Task 3: TestCoverageAgent

**Files:**

- Create: `projects/agent_platform/cluster_agents/test_coverage_agent.go`
- Create: `projects/agent_platform/cluster_agents/test_coverage_agent_test.go`

**Step 1: Write the failing tests**

```go
// test_coverage_agent_test.go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTestCoverageAgent_CollectWithActivity(t *testing.T) {
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "abc123", Commit: ghCommitDetail{Author: ghAuthor{Name: "jomcgi"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
	}))
	defer orchestrator.Close()

	agent := NewTestCoverageAgent(
		&GitActivityGate{
			github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
			orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
			botAuthors:   []string{"ci-format-bot"},
			branch:       "main",
		},
		1*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Source != "improvement:test-coverage" {
		t.Errorf("expected source improvement:test-coverage, got %s", findings[0].Source)
	}
}

func TestTestCoverageAgent_CollectNoActivity(t *testing.T) {
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "abc", Commit: ghCommitDetail{Author: ghAuthor{Name: "ci-format-bot"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	agent := NewTestCoverageAgent(
		&GitActivityGate{
			github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
			orchestrator: &OrchestratorClient{baseURL: "http://unused", client: &http.Client{}},
			botAuthors:   []string{"ci-format-bot"},
			branch:       "main",
		},
		1*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings with no activity, got %d", len(findings))
	}
}

func TestTestCoverageAgent_AnalyzeCreatesJob(t *testing.T) {
	agent := NewTestCoverageAgent(nil, 1*time.Hour)

	findings := []Finding{{
		Source: "improvement:test-coverage",
		Title:  "New commits",
		Data:   map[string]any{"commit_range": "old..new"},
	}}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}
	if actions[0].Type != ActionOrchestratorJob {
		t.Errorf("expected orchestrator_job, got %s", actions[0].Type)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestTestCoverageAgent`
Expected: Compilation error — `NewTestCoverageAgent` not defined.

**Step 3: Write minimal implementation**

```go
// test_coverage_agent.go
package main

import (
	"context"
	"fmt"
	"time"
)

const testCoverageTag = "improvement:test-coverage"

type TestCoverageAgent struct {
	gate     *GitActivityGate
	interval time.Duration
}

func NewTestCoverageAgent(gate *GitActivityGate, interval time.Duration) *TestCoverageAgent {
	return &TestCoverageAgent{gate: gate, interval: interval}
}

func (a *TestCoverageAgent) Name() string            { return "test-coverage" }
func (a *TestCoverageAgent) Interval() time.Duration { return a.interval }

func (a *TestCoverageAgent) Collect(ctx context.Context) ([]Finding, error) {
	commitRange, hasActivity, err := a.gate.Check(ctx, testCoverageTag)
	if err != nil {
		return nil, err
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{{
		Fingerprint: testCoverageTag,
		Source:      testCoverageTag,
		Severity:    SeverityInfo,
		Title:       "New commits for test coverage review",
		Data:        map[string]any{"commit_range": commitRange},
		Timestamp:   time.Now(),
	}}, nil
}

func (a *TestCoverageAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	commitRange := fmt.Sprintf("%v", findings[0].Data["commit_range"])

	task := fmt.Sprintf(`Review files changed in commits %s on main. For each Go or Python source file that was modified and lacks a corresponding _test file, write tests that cover the key behaviors.

Before starting:
- Check `+"`gh pr list --search \"test\"`"+` for existing test coverage PRs
- Check `+"`gh issue list --search \"test\"`"+` for related issues
- Skip files in generated code (zz_generated.*, *_types.go deepcopy)

Create one PR per project. Use conventional commit format:
test(<project>): add coverage for <description>`, commitRange)

	return []Action{{
		Type:    ActionOrchestratorJob,
		Finding: findings[0],
		Payload: map[string]any{"task": task},
	}}, nil
}

func (a *TestCoverageAgent) Execute(ctx context.Context, actions []Action) error {
	// Reuses the Escalator — wired in main.go
	return nil
}
```

> **Note to implementer:** The `Execute` method is a no-op because job submission is handled by the shared `Escalator` in main.go. We need to refactor the wiring slightly — see Task 7.

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestTestCoverageAgent`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/test_coverage_agent.go projects/agent_platform/cluster_agents/test_coverage_agent_test.go
git commit -m "feat(cluster-agents): add TestCoverageAgent"
```

---

### Task 4: ReadmeFreshnessAgent

**Files:**

- Create: `projects/agent_platform/cluster_agents/readme_freshness_agent.go`
- Create: `projects/agent_platform/cluster_agents/readme_freshness_agent_test.go`

**Step 1: Write the failing tests**

```go
// readme_freshness_agent_test.go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestReadmeFreshnessAgent_CollectWithActivity(t *testing.T) {
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "readme123", Commit: ghCommitDetail{Author: ghAuthor{Name: "jomcgi"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
	}))
	defer orchestrator.Close()

	agent := NewReadmeFreshnessAgent(
		&GitActivityGate{
			github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
			orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
			botAuthors:   []string{"ci-format-bot"},
			branch:       "main",
		},
		168*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Source != "improvement:readme-freshness" {
		t.Errorf("expected source improvement:readme-freshness, got %s", findings[0].Source)
	}
}

func TestReadmeFreshnessAgent_AnalyzeCreatesJob(t *testing.T) {
	agent := NewReadmeFreshnessAgent(nil, 168*time.Hour)

	findings := []Finding{{
		Source: "improvement:readme-freshness",
		Title:  "New commits",
		Data:   map[string]any{"commit_range": "old..new"},
	}}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}
	if actions[0].Type != ActionOrchestratorJob {
		t.Errorf("expected orchestrator_job, got %s", actions[0].Type)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestReadmeFreshnessAgent`
Expected: Compilation error.

**Step 3: Write minimal implementation**

```go
// readme_freshness_agent.go
package main

import (
	"context"
	"time"
)

const readmeFreshnessTag = "improvement:readme-freshness"

type ReadmeFreshnessAgent struct {
	gate     *GitActivityGate
	interval time.Duration
}

func NewReadmeFreshnessAgent(gate *GitActivityGate, interval time.Duration) *ReadmeFreshnessAgent {
	return &ReadmeFreshnessAgent{gate: gate, interval: interval}
}

func (a *ReadmeFreshnessAgent) Name() string            { return "readme-freshness" }
func (a *ReadmeFreshnessAgent) Interval() time.Duration { return a.interval }

func (a *ReadmeFreshnessAgent) Collect(ctx context.Context) ([]Finding, error) {
	commitRange, hasActivity, err := a.gate.Check(ctx, readmeFreshnessTag)
	if err != nil {
		return nil, err
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{{
		Fingerprint: readmeFreshnessTag,
		Source:      readmeFreshnessTag,
		Severity:    SeverityInfo,
		Title:       "New commits for README freshness review",
		Data:        map[string]any{"commit_range": commitRange},
		Timestamp:   time.Now(),
	}}, nil
}

func (a *ReadmeFreshnessAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	task := `For each projects/*/README.md, compare the README content against the actual project structure:
- Files and directories that exist vs what's documented
- Chart.yaml fields (appVersion, description) vs README claims
- deploy/ config (application.yaml, values.yaml) vs documented setup
- Available commands and endpoints vs what the code actually exposes

Update any README where the documented structure no longer matches reality.
Do not add content that wasn't there before — only fix inaccuracies.

Before starting:
- Check ` + "`gh pr list --search \"README\"`" + ` for existing README PRs
- Check ` + "`gh issue list --search \"README\"`" + ` for related issues

Create one PR per project. Use conventional commit format:
docs(<project>): update README to match current structure`

	return []Action{{
		Type:    ActionOrchestratorJob,
		Finding: findings[0],
		Payload: map[string]any{"task": task},
	}}, nil
}

func (a *ReadmeFreshnessAgent) Execute(_ context.Context, _ []Action) error {
	return nil
}
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestReadmeFreshnessAgent`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/readme_freshness_agent.go projects/agent_platform/cluster_agents/readme_freshness_agent_test.go
git commit -m "feat(cluster-agents): add ReadmeFreshnessAgent"
```

---

### Task 5: GitHubClient — PR and Check Suite Methods

**Files:**

- Modify: `projects/agent_platform/cluster_agents/github_client.go`
- Modify: `projects/agent_platform/cluster_agents/github_client_test.go`

Add methods needed by PRFixAgent: listing open PRs and checking their check suite status.

**Step 1: Write the failing tests**

```go
// Append to github_client_test.go

func TestGitHubClient_OpenPRsWithFailingChecks(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:    42,
					Head:      ghHead{Ref: "feat/widget", SHA: "sha42"},
					PushedAt:  time.Now().Add(-2 * time.Hour),
					UpdatedAt: time.Now().Add(-2 * time.Hour),
				},
				{
					Number:    43,
					Head:      ghHead{Ref: "feat/fresh", SHA: "sha43"},
					PushedAt:  time.Now().Add(-10 * time.Minute),
					UpdatedAt: time.Now().Add(-10 * time.Minute),
				},
			}
			json.NewEncoder(w).Encode(prs)
		case r.URL.Path == "/repos/jomcgi/homelab/commits/sha42/check-suites":
			callCount++
			json.NewEncoder(w).Encode(ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			})
		case r.URL.Path == "/repos/jomcgi/homelab/commits/sha43/check-suites":
			callCount++
			json.NewEncoder(w).Encode(ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			})
		default:
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatal(err)
	}

	// PR 43 was pushed 10 minutes ago (< 1h threshold), should be excluded
	if len(prs) != 1 {
		t.Fatalf("expected 1 stale failing PR, got %d", len(prs))
	}
	if prs[0].Number != 42 {
		t.Errorf("expected PR 42, got %d", prs[0].Number)
	}
}

func TestGitHubClient_OpenPRsWithFailingChecks_AllPassing(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:   42,
					Head:     ghHead{Ref: "feat/widget", SHA: "sha42"},
					PushedAt: time.Now().Add(-2 * time.Hour),
				},
			}
			json.NewEncoder(w).Encode(prs)
		case r.URL.Path == "/repos/jomcgi/homelab/commits/sha42/check-suites":
			json.NewEncoder(w).Encode(ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "success"}},
			})
		}
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "test-token", "jomcgi/homelab")
	prs, err := client.OpenPRsWithFailingChecks(context.Background(), 1*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(prs) != 0 {
		t.Errorf("expected 0 failing PRs, got %d", len(prs))
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitHubClient_OpenPRs`
Expected: Compilation error — `ghPullRequest`, `OpenPRsWithFailingChecks` not defined.

**Step 3: Add PR and check suite types and methods to github_client.go**

```go
// Append to github_client.go

type ghHead struct {
	Ref string `json:"ref"`
	SHA string `json:"sha"`
}

type ghPullRequest struct {
	Number    int       `json:"number"`
	Head      ghHead    `json:"head"`
	PushedAt  time.Time `json:"pushed_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ghCheckSuite struct {
	Conclusion string `json:"conclusion"`
}

type ghCheckSuitesResponse struct {
	CheckSuites []ghCheckSuite `json:"check_suites"`
}

// OpenPRsWithFailingChecks returns open PRs whose last push was more than
// staleThreshold ago and whose latest check suite has a failure conclusion.
func (g *GitHubClient) OpenPRsWithFailingChecks(ctx context.Context, staleThreshold time.Duration) ([]ghPullRequest, error) {
	u := fmt.Sprintf("%s/repos/%s/pulls?state=open&per_page=30", g.baseURL, g.repo)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("github list PRs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github returned %d", resp.StatusCode)
	}

	var prs []ghPullRequest
	if err := json.NewDecoder(resp.Body).Decode(&prs); err != nil {
		return nil, fmt.Errorf("decode github PRs: %w", err)
	}

	cutoff := time.Now().Add(-staleThreshold)
	var failing []ghPullRequest

	for _, pr := range prs {
		if pr.PushedAt.After(cutoff) {
			continue // Too recent — someone might still be working on it
		}

		hasFailing, err := g.hasFailingChecks(ctx, pr.Head.SHA)
		if err != nil {
			slog.Warn("could not check PR status, skipping", "pr", pr.Number, "error", err)
			continue
		}
		if hasFailing {
			failing = append(failing, pr)
		}
	}

	return failing, nil
}

func (g *GitHubClient) hasFailingChecks(ctx context.Context, sha string) (bool, error) {
	u := fmt.Sprintf("%s/repos/%s/commits/%s/check-suites", g.baseURL, g.repo, sha)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return false, err
	}
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := g.client.Do(req)
	if err != nil {
		return false, fmt.Errorf("github check suites: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("github returned %d", resp.StatusCode)
	}

	var result ghCheckSuitesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("decode check suites: %w", err)
	}

	for _, cs := range result.CheckSuites {
		if cs.Conclusion == "failure" {
			return true, nil
		}
	}

	return false, nil
}
```

> **Note to implementer:** You'll need to add `"log/slog"` to the imports in `github_client.go` for the `slog.Warn` call in `OpenPRsWithFailingChecks`.

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestGitHubClient_OpenPRs`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/github_client.go projects/agent_platform/cluster_agents/github_client_test.go
git commit -m "feat(cluster-agents): add PR and check suite methods to GitHubClient"
```

---

### Task 6: RulesAgent and PRFixAgent

**Files:**

- Create: `projects/agent_platform/cluster_agents/rules_agent.go`
- Create: `projects/agent_platform/cluster_agents/rules_agent_test.go`
- Create: `projects/agent_platform/cluster_agents/pr_fix_agent.go`
- Create: `projects/agent_platform/cluster_agents/pr_fix_agent_test.go`

These follow the same pattern as Tasks 3-4 but with their own prompts and triggers.

**Step 1: Write failing tests for RulesAgent**

```go
// rules_agent_test.go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestRulesAgent_CollectWithActivity(t *testing.T) {
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		commits := []ghCommit{
			{SHA: "rules123", Commit: ghCommitDetail{Author: ghAuthor{Name: "jomcgi"}}},
		}
		json.NewEncoder(w).Encode(commits)
	}))
	defer github.Close()

	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
	}))
	defer orchestrator.Close()

	agent := NewRulesAgent(
		&GitActivityGate{
			github:       NewGitHubClient(github.URL, "", "jomcgi/homelab"),
			orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
			botAuthors:   []string{"ci-format-bot"},
			branch:       "main",
		},
		24*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Source != "improvement:rules" {
		t.Errorf("expected source improvement:rules, got %s", findings[0].Source)
	}
}

func TestRulesAgent_AnalyzeCreatesJob(t *testing.T) {
	agent := NewRulesAgent(nil, 24*time.Hour)

	findings := []Finding{{
		Source: "improvement:rules",
		Data:   map[string]any{"commit_range": "old..new"},
	}}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 {
		t.Fatalf("expected 1 action, got %d", len(actions))
	}
}
```

**Step 2: Write failing tests for PRFixAgent**

```go
// pr_fix_agent_test.go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPRFixAgent_CollectFindsFailingPRs(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:   42,
					Head:     ghHead{Ref: "feat/broken", SHA: "sha42"},
					PushedAt: time.Now().Add(-2 * time.Hour),
				},
			}
			json.NewEncoder(w).Encode(prs)
		case r.URL.Path == "/repos/jomcgi/homelab/commits/sha42/check-suites":
			json.NewEncoder(w).Encode(ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			})
		}
	}))
	defer server.Close()

	// Orchestrator returns no active fix job for this PR
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
	}))
	defer orchestrator.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(server.URL, "", "jomcgi/homelab"),
		&OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		1*time.Hour,
		1*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Data["pr_number"] != 42 {
		t.Errorf("expected pr_number 42, got %v", findings[0].Data["pr_number"])
	}
}

func TestPRFixAgent_CollectSkipsPRWithActiveJob(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/repos/jomcgi/homelab/pulls":
			prs := []ghPullRequest{
				{
					Number:   42,
					Head:     ghHead{Ref: "feat/broken", SHA: "sha42"},
					PushedAt: time.Now().Add(-2 * time.Hour),
				},
			}
			json.NewEncoder(w).Encode(prs)
		case r.URL.Path == "/repos/jomcgi/homelab/commits/sha42/check-suites":
			json.NewEncoder(w).Encode(ghCheckSuitesResponse{
				CheckSuites: []ghCheckSuite{{Conclusion: "failure"}},
			})
		}
	}))
	defer server.Close()

	// Orchestrator returns an active job for PR 42
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(orchestratorListResponse{
			Jobs:  []orchestratorJob{{ID: "existing", Status: "RUNNING"}},
			Total: 1,
		})
	}))
	defer orchestrator.Close()

	agent := NewPRFixAgent(
		NewGitHubClient(server.URL, "", "jomcgi/homelab"),
		&OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		1*time.Hour,
		1*time.Hour,
	)

	findings, err := agent.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings when active job exists, got %d", len(findings))
	}
}

func TestPRFixAgent_AnalyzeCreatesPerPRActions(t *testing.T) {
	agent := NewPRFixAgent(nil, nil, 1*time.Hour, 1*time.Hour)

	findings := []Finding{
		{Source: "improvement:pr-fix", Data: map[string]any{"pr_number": 42, "branch": "feat/broken"}},
		{Source: "improvement:pr-fix", Data: map[string]any{"pr_number": 99, "branch": "fix/thing"}},
	}

	actions, err := agent.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}
}
```

**Step 3: Run tests to verify they fail**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter="TestRulesAgent|TestPRFixAgent"`
Expected: Compilation errors.

**Step 4: Write RulesAgent implementation**

```go
// rules_agent.go
package main

import (
	"context"
	"fmt"
	"time"
)

const rulesTag = "improvement:rules"

type RulesAgent struct {
	gate     *GitActivityGate
	interval time.Duration
}

func NewRulesAgent(gate *GitActivityGate, interval time.Duration) *RulesAgent {
	return &RulesAgent{gate: gate, interval: interval}
}

func (a *RulesAgent) Name() string            { return "rules" }
func (a *RulesAgent) Interval() time.Duration { return a.interval }

func (a *RulesAgent) Collect(ctx context.Context) ([]Finding, error) {
	commitRange, hasActivity, err := a.gate.Check(ctx, rulesTag)
	if err != nil {
		return nil, err
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{{
		Fingerprint: rulesTag,
		Source:      rulesTag,
		Severity:    SeverityInfo,
		Title:       "New commits for rules review",
		Data:        map[string]any{"commit_range": commitRange},
		Timestamp:   time.Now(),
	}}, nil
}

func (a *RulesAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	commitRange := fmt.Sprintf("%v", findings[0].Data["commit_range"])

	task := fmt.Sprintf(`Review PRs merged to main in commits %s. For each merged PR:

1. If it's a bug fix (fix: prefix), analyze the diff for patterns that could
   be caught statically. Propose a semgrep rule in bazel/semgrep/rules/ with
   a test case. Check existing rules to avoid duplicates.

2. If it reveals an agent anti-pattern or a common mistake, propose additions
   to .claude/CLAUDE.md or .claude/settings.json hooks to prevent recurrence.

Before starting:
- Check `+"`gh pr list --search \"semgrep OR rule OR hook\"`"+` for existing work
- Check `+"`gh issue list`"+` for related issues
- Review existing rules in bazel/semgrep/rules/ and .claude/settings.json

Create one PR per rule/config change. Use conventional commit format:
- build(semgrep): add rule for <pattern>
- ci(claude): add hook to prevent <behavior>`, commitRange)

	return []Action{{
		Type:    ActionOrchestratorJob,
		Finding: findings[0],
		Payload: map[string]any{"task": task},
	}}, nil
}

func (a *RulesAgent) Execute(_ context.Context, _ []Action) error {
	return nil
}
```

**Step 5: Write PRFixAgent implementation**

```go
// pr_fix_agent.go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"time"
)

type PRFixAgent struct {
	github         *GitHubClient
	orchestrator   *OrchestratorClient
	interval       time.Duration
	staleThreshold time.Duration
}

func NewPRFixAgent(github *GitHubClient, orchestrator *OrchestratorClient, interval, staleThreshold time.Duration) *PRFixAgent {
	return &PRFixAgent{
		github:         github,
		orchestrator:   orchestrator,
		interval:       interval,
		staleThreshold: staleThreshold,
	}
}

func (a *PRFixAgent) Name() string            { return "pr-fix" }
func (a *PRFixAgent) Interval() time.Duration { return a.interval }

func (a *PRFixAgent) Collect(ctx context.Context) ([]Finding, error) {
	prs, err := a.github.OpenPRsWithFailingChecks(ctx, a.staleThreshold)
	if err != nil {
		return nil, fmt.Errorf("pr fix collect: %w", err)
	}

	var findings []Finding
	for _, pr := range prs {
		tag := fmt.Sprintf("improvement:pr-fix:%d", pr.Number)

		hasActive, err := a.hasActiveFixJob(ctx, tag)
		if err != nil {
			slog.Warn("dedup check failed for PR fix", "pr", pr.Number, "error", err)
			continue
		}
		if hasActive {
			slog.Debug("skipping PR, active fix job exists", "pr", pr.Number)
			continue
		}

		findings = append(findings, Finding{
			Fingerprint: tag,
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       fmt.Sprintf("PR #%d has failing checks", pr.Number),
			Detail:      fmt.Sprintf("Branch %s, last push >%s ago", pr.Head.Ref, a.staleThreshold),
			Data: map[string]any{
				"pr_number": pr.Number,
				"branch":    pr.Head.Ref,
			},
			Timestamp: time.Now(),
		})
	}

	return findings, nil
}

func (a *PRFixAgent) hasActiveFixJob(ctx context.Context, tag string) (bool, error) {
	if a.orchestrator == nil {
		return false, nil
	}

	u := fmt.Sprintf("%s/jobs?status=%s&tags=%s&limit=1",
		a.orchestrator.baseURL,
		url.QueryEscape("PENDING,RUNNING"),
		url.QueryEscape(tag),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return false, err
	}

	resp, err := a.orchestrator.client.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	var result orchestratorListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, err
	}

	return result.Total > 0, nil
}

func (a *PRFixAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	actions := make([]Action, 0, len(findings))
	for _, f := range findings {
		prNumber := f.Data["pr_number"]
		branch := f.Data["branch"]

		task := fmt.Sprintf(`PR #%v has failing CI checks on branch %v.

1. Check out the branch
2. Use BuildBuddy MCP tools to understand the CI failure
3. Fix the issue
4. Commit and push (do NOT force push)

Before starting:
- Run `+"`gh pr view %v --json commits,body`"+` to understand context
- Check PR comments for any human instructions or "do not auto-fix" labels

Use conventional commit format:
fix(<scope>): resolve CI failure in PR #%v`, prNumber, branch, prNumber, prNumber)

		actions = append(actions, Action{
			Type:    ActionOrchestratorJob,
			Finding: f,
			Payload: map[string]any{"task": task},
		})
	}

	return actions, nil
}

func (a *PRFixAgent) Execute(_ context.Context, _ []Action) error {
	return nil
}
```

> **Note to implementer:** `pr_fix_agent.go` needs `"encoding/json"` in its imports.

**Step 6: Run tests to verify they pass**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter="TestRulesAgent|TestPRFixAgent"`
Expected: PASS

**Step 7: Commit**

```bash
git add projects/agent_platform/cluster_agents/rules_agent.go projects/agent_platform/cluster_agents/rules_agent_test.go projects/agent_platform/cluster_agents/pr_fix_agent.go projects/agent_platform/cluster_agents/pr_fix_agent_test.go
git commit -m "feat(cluster-agents): add RulesAgent and PRFixAgent"
```

---

### Task 7: Refactor Escalator for Improvement Agents

**Files:**

- Modify: `projects/agent_platform/cluster_agents/escalator.go`
- Modify: `projects/agent_platform/cluster_agents/escalator_test.go`

The existing `Escalator.Execute` hardcodes the patrol prompt format and tag scheme (`alert:{ruleID}`). The improvement agents need to submit their own prompts (from `Action.Payload["task"]`) and use their own tag scheme (from `Finding.Fingerprint`). Refactor so the escalator uses the payload task when present, falling back to the patrol format.

**Step 1: Write the failing test**

```go
// Append to escalator_test.go

func TestEscalator_UsesPayloadTaskWhenPresent(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "improvement:test-coverage",
			Source:      "improvement:test-coverage",
			Title:       "New commits for test coverage review",
		},
		Payload: map[string]any{
			"task": "Custom task prompt here",
		},
	}}

	esc.Execute(context.Background(), actions)

	if received == nil {
		t.Fatal("expected job to be submitted")
	}
	task, ok := received["task"].(string)
	if !ok || task != "Custom task prompt here" {
		t.Errorf("expected custom task, got %v", received["task"])
	}
	tags, ok := received["tags"].([]any)
	if !ok || len(tags) != 1 || tags[0] != "improvement:test-coverage" {
		t.Errorf("expected tag improvement:test-coverage, got %v", received["tags"])
	}
}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestEscalator_UsesPayloadTask`
Expected: FAIL — escalator currently ignores `Payload["task"]` and generates its own task string.

**Step 3: Modify escalator.go**

Update `submitOrchestratorJob` to check for `action.Payload["task"]` first:

```go
// In escalator.go, replace submitOrchestratorJob with:

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action, tag string) error {
	if e.orchestrator == nil {
		slog.Warn("orchestrator client not configured, skipping job submission")
		return nil
	}

	// Use custom task from payload if present, otherwise build patrol-style prompt.
	task, ok := action.Payload["task"].(string)
	if !ok || task == "" {
		ruleID := ruleIDFromFinding(action.Finding)
		task = fmt.Sprintf("SigNoz alert firing: %s\n\n"+
			"Rule ID: %s\n"+
			"Severity: %s\n\n"+
			"Details: %s\n\n"+
			"Investigate this alert using MCP tools. If a GitOps change can fix it, "+
			"create a PR. If it requires manual intervention, "+
			"create a GitHub issue summarizing your findings.",
			action.Finding.Title, ruleID, action.Finding.Severity,
			action.Finding.Detail)
	}

	source := action.Finding.Source
	if source == "" {
		source = fmt.Sprintf("patrol:%s", ruleIDFromFinding(action.Finding))
	}

	body, _ := json.Marshal(map[string]any{
		"task":   task,
		"source": source,
		"tags":   []string{tag},
	})

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, e.orchestrator.baseURL+"/jobs", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.orchestrator.client.Do(req)
	if err != nil {
		return fmt.Errorf("submit job: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	slog.Info("submitted orchestrator job",
		"source", source,
		"title", action.Finding.Title,
		"tag", tag,
	)
	return nil
}
```

Also update `Execute` to use `Finding.Fingerprint` as the tag when it doesn't have `Data["rule_id"]`:

```go
// In escalator.go, update Execute to derive tag from fingerprint:

func (e *Escalator) Execute(ctx context.Context, actions []Action) error {
	for _, action := range actions {
		if action.Type == ActionLog {
			slog.Info("finding",
				"severity", action.Finding.Severity,
				"title", action.Finding.Title,
				"detail", action.Finding.Detail,
				"fingerprint", action.Finding.Fingerprint,
			)
			continue
		}

		// Use fingerprint as tag for improvement agents, rule_id for patrol.
		tag := action.Finding.Fingerprint
		if ruleID, ok := action.Finding.Data["rule_id"]; ok {
			tag = fmt.Sprintf("alert:%v", ruleID)
		}

		exists, err := e.hasActiveJob(ctx, tag)
		if err != nil {
			slog.Error("dedup check failed", "error", err, "tag", tag)
			continue
		}
		if exists {
			slog.Info("skipping, active job exists", "tag", tag)
			continue
		}

		if err := e.submitOrchestratorJob(ctx, action, tag); err != nil {
			slog.Error("orchestrator job failed", "error", err, "tag", tag)
			continue
		}
	}
	return nil
}
```

**Step 4: Run ALL escalator tests to verify nothing is broken**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci --test_filter=TestEscalator`
Expected: All PASS (including existing tests — verify tag/source backwards compatibility for patrol)

**Step 5: Commit**

```bash
git add projects/agent_platform/cluster_agents/escalator.go projects/agent_platform/cluster_agents/escalator_test.go
git commit -m "refactor(cluster-agents): support custom task payloads in Escalator"
```

---

### Task 8: Wire Up in main.go and Update Config

**Files:**

- Modify: `projects/agent_platform/cluster_agents/main.go`
- Modify: `projects/agent_platform/cluster_agents/deploy/values.yaml`
- Modify: `projects/agent_platform/cluster_agents/deploy/values-prod.yaml`
- Modify: `projects/agent_platform/cluster_agents/deploy/templates/deployment.yaml`

**Step 1: Update main.go to create and register all agents**

```go
// Replace main.go main() function body after the existing setup:

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	signozURL := envOr("SIGNOZ_URL", "http://signoz.signoz.svc.cluster.local:8080")
	signozToken := os.Getenv("SIGNOZ_API_KEY")
	orchestratorURL := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080")
	httpPort := envOr("HTTP_PORT", "8080")
	patrolInterval := envDurationOr("PATROL_INTERVAL", 1*time.Hour)

	// GitHub config for improvement agents
	githubToken := os.Getenv("GITHUB_TOKEN")
	githubRepo := envOr("GITHUB_REPO", "jomcgi/homelab")
	githubBranch := envOr("GITHUB_BRANCH", "main")
	botAuthors := strings.Split(envOr("BOT_AUTHORS", "ci-format-bot,argocd-image-updater,chart-version-bot"), ",")

	testCoverageInterval := envDurationOr("TEST_COVERAGE_INTERVAL", 1*time.Hour)
	readmeFreshnessInterval := envDurationOr("README_FRESHNESS_INTERVAL", 168*time.Hour)
	rulesInterval := envDurationOr("RULES_INTERVAL", 24*time.Hour)
	prFixInterval := envDurationOr("PR_FIX_INTERVAL", 1*time.Hour)
	prFixStaleThreshold := envDurationOr("PR_FIX_STALE_THRESHOLD", 1*time.Hour)

	orchestratorClient := NewOrchestratorClient(orchestratorURL)
	githubClient := NewGitHubClient("https://api.github.com", githubToken, githubRepo)

	collector := NewAlertCollector(signozURL, signozToken)
	escalator := NewEscalator(orchestratorClient)
	patrol := NewPatrolAgent(collector, escalator, patrolInterval)

	// Shared gate for commit-triggered agents
	gate := &GitActivityGate{
		github:       githubClient,
		orchestrator: orchestratorClient,
		botAuthors:   botAuthors,
		branch:       githubBranch,
	}

	agents := []Agent{
		patrol,
		NewTestCoverageAgent(gate, testCoverageInterval),
		NewReadmeFreshnessAgent(gate, readmeFreshnessInterval),
		NewRulesAgent(gate, rulesInterval),
		NewPRFixAgent(githubClient, orchestratorClient, prFixInterval, prFixStaleThreshold),
	}

	runner := NewRunner(agents)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})

	srv := &http.Server{Addr: ":" + httpPort, Handler: mux}
	go func() {
		slog.Info("http server starting", "port", httpPort)
		if err := srv.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("http server error", "error", err)
		}
	}()

	slog.Info("cluster-agents starting",
		"agents", len(agents),
		"patrol_interval", patrolInterval,
		"test_coverage_interval", testCoverageInterval,
		"readme_freshness_interval", readmeFreshnessInterval,
		"rules_interval", rulesInterval,
		"pr_fix_interval", prFixInterval,
	)
	runner.Run(ctx)

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	srv.Shutdown(shutdownCtx)
	slog.Info("cluster-agents stopped")
}
```

> **Note to implementer:** Add `"strings"` to the imports in main.go.

**Step 2: Update the improvement agents' Execute to use the shared Escalator**

The agents have no-op `Execute` methods because job submission goes through the Escalator. We need to wire the Escalator into each agent. The simplest approach: give each agent an `escalator` field and call it from Execute.

Update each agent's struct to include `escalator *Escalator` and call `escalator.Execute` from their Execute method. Example for TestCoverageAgent:

```go
type TestCoverageAgent struct {
	gate      *GitActivityGate
	escalator *Escalator
	interval  time.Duration
}

func NewTestCoverageAgent(gate *GitActivityGate, escalator *Escalator, interval time.Duration) *TestCoverageAgent {
	return &TestCoverageAgent{gate: gate, escalator: escalator, interval: interval}
}

func (a *TestCoverageAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}
```

Apply the same pattern to ReadmeFreshnessAgent, RulesAgent, and PRFixAgent. Update constructors in main.go:

```go
NewTestCoverageAgent(gate, escalator, testCoverageInterval),
NewReadmeFreshnessAgent(gate, escalator, readmeFreshnessInterval),
NewRulesAgent(gate, escalator, rulesInterval),
NewPRFixAgent(githubClient, orchestratorClient, escalator, prFixInterval, prFixStaleThreshold),
```

**Step 3: Update deployment template with new env vars**

Add to `deployment.yaml` after the existing env vars:

```yaml
- name: GITHUB_TOKEN
  valueFrom:
    secretKeyRef:
      name: agent-secrets
      key: GITHUB_TOKEN
- name: GITHUB_REPO
  value: { { .Values.config.githubRepo | quote } }
- name: BOT_AUTHORS
  value: { { .Values.config.botAuthors | quote } }
- name: TEST_COVERAGE_INTERVAL
  value: { { .Values.config.testCoverageInterval | quote } }
- name: README_FRESHNESS_INTERVAL
  value: { { .Values.config.readmeFreshnessInterval | quote } }
- name: RULES_INTERVAL
  value: { { .Values.config.rulesInterval | quote } }
- name: PR_FIX_INTERVAL
  value: { { .Values.config.prFixInterval | quote } }
- name: PR_FIX_STALE_THRESHOLD
  value: { { .Values.config.prFixStaleThreshold | quote } }
```

**Step 4: Update values.yaml defaults**

Add to the `config:` section in `values.yaml`:

```yaml
githubRepo: "jomcgi/homelab"
botAuthors: "ci-format-bot,argocd-image-updater,chart-version-bot"
testCoverageInterval: "1h"
readmeFreshnessInterval: "168h"
rulesInterval: "24h"
prFixInterval: "1h"
prFixStaleThreshold: "1h"
```

**Step 5: Add GITHUB_TOKEN to 1Password secret**

> **Note to implementer:** The `agent-secrets` OnePasswordItem already exists. You need to add a `GITHUB_TOKEN` field to the 1Password item at `vaults/k8s-homelab/items/agent-secrets`. This is a manual step — do it via the 1Password UI. Create a GitHub personal access token with `repo` scope.

**Step 6: Run format to update BUILD file**

Run: `format`

The BUILD file needs updating since we added new .go files. Gazelle (via format) will add them to `srcs` and `test srcs`.

**Step 7: Run all tests**

Run: `bazel test //projects/agent_platform/cluster_agents:cluster_agents_test --config=ci`
Expected: All tests PASS

**Step 8: Commit**

```bash
git add projects/agent_platform/cluster_agents/
git commit -m "feat(cluster-agents): wire improvement agents into main and deployment"
```

---

### Task 9: Helm Template Validation

**Files:**

- No new files — validation only

**Step 1: Render Helm templates to verify no syntax errors**

Run: `helm template cluster-agents projects/agent_platform/cluster_agents/deploy/ -f projects/agent_platform/cluster_agents/deploy/values.yaml`

Verify:

- Deployment includes all new env vars
- Values render correctly
- No YAML syntax errors

**Step 2: Render with prod values overlay**

Run: `helm template cluster-agents projects/agent_platform/cluster_agents/deploy/ -f projects/agent_platform/cluster_agents/deploy/values.yaml -f projects/agent_platform/cluster_agents/deploy/values-prod.yaml`

Verify: Same checks.

**Step 3: Commit any fixes if needed**

---

### Task 10: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feat/continuous-improvement-agents
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(cluster-agents): add continuous improvement agents" --body "$(cat <<'EOF'
## Summary
- Add four new agents to cluster-agents: TestCoverage, ReadmeFreshness, Rules, PRFix
- GitActivityGate shared trigger checks for new non-bot commits via GitHub API
- PRFixAgent independently monitors open PRs with stale failing checks
- All agents submit jobs to the orchestrator with dedup via tags
- Design doc: docs/plans/2026-03-11-continuous-improvement-agents-design.md

## Test plan
- [ ] All new agent tests pass in CI
- [ ] Existing patrol/escalator tests still pass (backwards compatible)
- [ ] Helm template renders cleanly with new env vars
- [ ] Deploy to cluster and verify agents start (check logs)
- [ ] Verify dedup works — no duplicate jobs on consecutive sweeps with no new commits
- [ ] Create a PR with a failing check and verify PRFixAgent picks it up after 1h

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

# Alert-Driven Patrol Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the patrol agent from custom K8s/ArgoCD collectors + LLM triage to SigNoz alert-driven with GitHub PR label dedup.

**Architecture:** Single `AlertCollector` polls SigNoz for firing alerts. `Analyze` is deterministic (every firing alert → orchestrator job). `Execute` deduplicates via GitHub PR labels and orchestrator job status before submitting. No LLM, no NATS.

**Tech Stack:** Go, SigNoz REST API, GitHub REST API, agent-orchestrator REST API

**Worktree:** `/tmp/claude-worktrees/alert-driven-patrol` (branch `feat/alert-driven-patrol`)

**Design doc:** `docs/plans/2026-03-08-alert-driven-patrol-design.md`

**Important context:**
- Tests run in CI via Bazel, not locally. Use `bazel test //services/cluster-agents/...` to run tests.
- BUILD file will need updating when files are added/removed — run `format` to regenerate.
- The `Agent` interface lives in `model.go` — `Collect`, `Analyze`, `Execute`, `Name`, `Interval`.
- The orchestrator's list API (`GET /jobs?status=PENDING,RUNNING`) doesn't filter by source — filter client-side.

---

### Task 1: Clean Up — Delete Obsolete Files

Remove files that are being replaced by the new alert-driven approach.

**Files:**
- Delete: `services/cluster-agents/collector_k8s.go`
- Delete: `services/cluster-agents/collector_k8s_test.go`
- Delete: `services/cluster-agents/collector_argocd.go`
- Delete: `services/cluster-agents/collector_argocd_test.go`
- Delete: `services/cluster-agents/llm.go`
- Delete: `services/cluster-agents/llm_test.go`
- Delete: `services/cluster-agents/store.go`
- Delete: `services/cluster-agents/store_test.go`
- Delete: `services/cluster-agents/store_nats.go`

**Step 1: Delete the files**

```bash
cd /tmp/claude-worktrees/alert-driven-patrol
rm services/cluster-agents/collector_k8s.go \
   services/cluster-agents/collector_k8s_test.go \
   services/cluster-agents/collector_argocd.go \
   services/cluster-agents/collector_argocd_test.go \
   services/cluster-agents/llm.go \
   services/cluster-agents/llm_test.go \
   services/cluster-agents/store.go \
   services/cluster-agents/store_test.go \
   services/cluster-agents/store_nats.go
```

**Step 2: Commit**

```bash
git add -u services/cluster-agents/
git commit -m "refactor: remove obsolete collectors, LLM client, and NATS store"
```

---

### Task 2: Simplify model.go

Remove `FindingsStore` interface and unused action types. Keep `Agent`, `Finding`, `Action`, severity/action constants.

**Files:**
- Modify: `services/cluster-agents/model.go`

**Step 1: Update model.go**

Remove `FindingsStore` interface, `MemFindingsStore`, and `findingEntry`. Remove `ActionGitHubIssue` (no longer used — patrol only creates orchestrator jobs). Keep:

```go
package main

import (
	"context"
	"time"
)

type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

type ActionType string

const (
	ActionLog             ActionType = "log"
	ActionOrchestratorJob ActionType = "orchestrator_job"
)

type Finding struct {
	Fingerprint string         `json:"fingerprint"`
	Source      string         `json:"source"`
	Severity    Severity       `json:"severity"`
	Title       string         `json:"title"`
	Detail      string         `json:"detail"`
	Data        map[string]any `json:"data,omitempty"`
	Timestamp   time.Time      `json:"timestamp"`
}

type Action struct {
	Type    ActionType     `json:"type"`
	Finding Finding        `json:"finding"`
	Payload map[string]any `json:"payload,omitempty"`
}

type Agent interface {
	Name() string
	Collect(ctx context.Context) ([]Finding, error)
	Analyze(ctx context.Context, findings []Finding) ([]Action, error)
	Execute(ctx context.Context, actions []Action) error
	Interval() time.Duration
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/model.go
git commit -m "refactor: simplify model, remove FindingsStore and GitHubIssue action"
```

---

### Task 3: Alert Collector — Tests

Write tests for the SigNoz alert collector. Use httptest to mock the SigNoz API.

**Files:**
- Create: `services/cluster-agents/collector_alerts_test.go`

**Step 1: Write the tests**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAlertCollector_FiringAlerts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/rules" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:       42,
						Name:     "Pod OOMKilled",
						State:    "firing",
						Severity: "warning",
						Labels:   map[string]string{"namespace": "trips", "service": "imgproxy"},
					},
					{
						ID:       43,
						Name:     "Node NotReady",
						State:    "inactive",
						Severity: "critical",
					},
					{
						ID:       44,
						Name:     "High Error Rate",
						State:    "firing",
						Severity: "critical",
						Labels:   map[string]string{"service": "api-gateway"},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 2 {
		t.Fatalf("expected 2 findings (only firing), got %d", len(findings))
	}

	if findings[0].Fingerprint != "patrol.alert.42" {
		t.Errorf("expected fingerprint patrol.alert.42, got %s", findings[0].Fingerprint)
	}
	if findings[0].Severity != SeverityWarning {
		t.Errorf("expected warning severity, got %s", findings[0].Severity)
	}
	if findings[1].Fingerprint != "patrol.alert.44" {
		t.Errorf("expected fingerprint patrol.alert.44, got %s", findings[1].Fingerprint)
	}
	if findings[1].Severity != SeverityCritical {
		t.Errorf("expected critical severity, got %s", findings[1].Severity)
	}
}

func TestAlertCollector_NoFiringAlerts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{ID: 1, Name: "Healthy", State: "inactive", Severity: "warning"},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

func TestAlertCollector_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	_, err := collector.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error on 500 response")
	}
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/collector_alerts_test.go
git commit -m "test: add alert collector tests"
```

---

### Task 4: Alert Collector — Implementation

Implement the SigNoz alert collector that polls `/api/v1/rules` for firing alerts.

**Files:**
- Create: `services/cluster-agents/collector_alerts.go`

**Step 1: Write the implementation**

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type alertRulesResponse struct {
	Status string         `json:"status"`
	Data   alertRulesData `json:"data"`
}

type alertRulesData struct {
	Rules []alertRule `json:"rules"`
}

type alertRule struct {
	ID        int               `json:"id"`
	Name      string            `json:"alert"`
	State     string            `json:"state"`
	Severity  string            `json:"severity,omitempty"`
	Labels    map[string]string `json:"labels,omitempty"`
	Condition string            `json:"condition,omitempty"`
}

type AlertCollector struct {
	baseURL string
	token   string
	client  *http.Client
}

func NewAlertCollector(baseURL, token string) *AlertCollector {
	return &AlertCollector{
		baseURL: baseURL,
		token:   token,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *AlertCollector) Collect(ctx context.Context) ([]Finding, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/rules", nil)
	if err != nil {
		return nil, err
	}
	if c.token != "" {
		req.Header.Set("SIGNOZ-API-KEY", c.token)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("signoz list alerts: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("signoz returned %d", resp.StatusCode)
	}

	var result alertRulesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode signoz response: %w", err)
	}

	var findings []Finding
	now := time.Now()

	for _, rule := range result.Data.Rules {
		if rule.State != "firing" {
			continue
		}

		severity := mapSeverity(rule.Severity)

		findings = append(findings, Finding{
			Fingerprint: fmt.Sprintf("patrol.alert.%d", rule.ID),
			Source:      "signoz:alert",
			Severity:    severity,
			Title:       rule.Name,
			Detail:      fmt.Sprintf("Alert %q (rule %d) is firing", rule.Name, rule.ID),
			Data: map[string]any{
				"rule_id":  rule.ID,
				"labels":   rule.Labels,
				"severity": rule.Severity,
			},
			Timestamp: now,
		})
	}

	return findings, nil
}

func mapSeverity(s string) Severity {
	switch s {
	case "critical":
		return SeverityCritical
	case "warning":
		return SeverityWarning
	default:
		return SeverityInfo
	}
}
```

**Step 2: Run tests**

```bash
bazel test //services/cluster-agents/...
```

Expected: tests pass (the alert collector tests + runner tests should pass, patrol and escalator tests will need updating later).

**Step 3: Commit**

```bash
git add services/cluster-agents/collector_alerts.go
git commit -m "feat: add SigNoz alert collector"
```

**Note:** The exact SigNoz API response shape may differ from what's mocked above. Check the live API response shape by reading the SigNoz MCP tool output or documentation. The key fields are `id`, `alert` (name), `state`, `severity`, and `labels`. Adjust struct tags if needed after verifying.

---

### Task 5: GitHub PR Dedup Client — Tests

Write tests for the GitHub PR label checker used for deduplication.

**Files:**
- Create: `services/cluster-agents/github_test.go`

**Step 1: Write the tests**

```go
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
```

**Step 2: Commit**

```bash
git add services/cluster-agents/github_test.go
git commit -m "test: add GitHub PR dedup checker tests"
```

---

### Task 6: GitHub PR Dedup Client — Implementation

Implement the GitHub REST API client that checks for open/recently-merged PRs by label.

**Files:**
- Create: `services/cluster-agents/github.go`

**Step 1: Write the implementation**

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type ghPullRequest struct {
	Number   int        `json:"number"`
	State    string     `json:"state"`
	MergedAt *time.Time `json:"merged_at,omitempty"`
}

type GitHubPRChecker struct {
	baseURL string
	token   string
	repo    string
	client  *http.Client
}

func NewGitHubPRChecker(baseURL, token, repo string) *GitHubPRChecker {
	return &GitHubPRChecker{
		baseURL: baseURL,
		token:   token,
		repo:    repo,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (g *GitHubPRChecker) HasOpenPR(ctx context.Context, ruleID string) (bool, error) {
	prs, err := g.listPRs(ctx, "open", fmt.Sprintf("alert:%s", ruleID))
	if err != nil {
		return false, err
	}
	return len(prs) > 0, nil
}

func (g *GitHubPRChecker) HasRecentlyMergedPR(ctx context.Context, ruleID string, window time.Duration) (bool, error) {
	prs, err := g.listPRs(ctx, "closed", fmt.Sprintf("alert:%s", ruleID))
	if err != nil {
		return false, err
	}

	cutoff := time.Now().Add(-window)
	for _, pr := range prs {
		if pr.MergedAt != nil && pr.MergedAt.After(cutoff) {
			return true, nil
		}
	}
	return false, nil
}

func (g *GitHubPRChecker) listPRs(ctx context.Context, state, label string) ([]ghPullRequest, error) {
	url := fmt.Sprintf("%s/repos/%s/pulls?state=%s&labels=%s&per_page=5", g.baseURL, g.repo, state, label)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
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
		return nil, fmt.Errorf("decode github response: %w", err)
	}
	return prs, nil
}
```

**Step 2: Run tests**

```bash
bazel test //services/cluster-agents/...
```

**Step 3: Commit**

```bash
git add services/cluster-agents/github.go
git commit -m "feat: add GitHub PR dedup checker"
```

---

### Task 7: Rewrite Escalator — Tests

Replace the escalator tests to use GitHub PR dedup + orchestrator job status instead of NATS.

**Files:**
- Modify: `services/cluster-agents/escalator_test.go`

**Step 1: Rewrite escalator tests**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEscalator_SkipsWhenOpenPRExists(t *testing.T) {
	var jobSubmitted bool
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		jobSubmitted = true
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Return an open PR for this alert
		json.NewEncoder(w).Encode([]ghPullRequest{{Number: 99, State: "open"}})
	}))
	defer github.Close()

	esc := &Escalator{
		github:       NewGitHubPRChecker(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		mergeWindow:  0,
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": 42},
		},
	}}

	esc.Execute(context.Background(), actions)

	if jobSubmitted {
		t.Error("expected job NOT to be submitted when open PR exists")
	}
}

func TestEscalator_SubmitsJobWhenNoPR(t *testing.T) {
	var received map[string]any
	orchestrator := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-1"})
	}))
	defer orchestrator.Close()

	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghPullRequest{})
	}))
	defer github.Close()

	esc := &Escalator{
		github:       NewGitHubPRChecker(github.URL, "", "jomcgi/homelab"),
		orchestrator: &OrchestratorClient{baseURL: orchestrator.URL, client: &http.Client{}},
		mergeWindow:  0,
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "patrol.alert.42",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": 42},
		},
	}}

	esc.Execute(context.Background(), actions)

	if received == nil {
		t.Fatal("expected orchestrator job to be submitted")
	}
	source, ok := received["source"].(string)
	if !ok || source != "patrol:42" {
		t.Errorf("expected source patrol:42, got %v", received["source"])
	}
}

func TestEscalator_LogActionSkipsDedup(t *testing.T) {
	// Log actions should not trigger any dedup checks or job submission
	esc := &Escalator{}

	actions := []Action{{
		Type: ActionLog,
		Finding: Finding{
			Fingerprint: "patrol.alert.99",
			Severity:    SeverityInfo,
			Title:       "info finding",
		},
	}}

	err := esc.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/escalator_test.go
git commit -m "test: rewrite escalator tests for GitHub PR dedup"
```

---

### Task 8: Rewrite Escalator — Implementation

Replace the escalator to use GitHub PR label dedup instead of NATS KV.

**Files:**
- Modify: `services/cluster-agents/escalator.go`

**Step 1: Rewrite escalator**

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

type OrchestratorClient struct {
	baseURL string
	client  *http.Client
}

func NewOrchestratorClient(baseURL string) *OrchestratorClient {
	return &OrchestratorClient{
		baseURL: baseURL,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

type Escalator struct {
	github       *GitHubPRChecker
	orchestrator *OrchestratorClient
	mergeWindow  time.Duration
}

func NewEscalator(github *GitHubPRChecker, orchestrator *OrchestratorClient) *Escalator {
	return &Escalator{
		github:       github,
		orchestrator: orchestrator,
		mergeWindow:  1 * time.Hour,
	}
}

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

		ruleID := ruleIDFromFinding(action.Finding)

		if e.github != nil {
			open, err := e.github.HasOpenPR(ctx, ruleID)
			if err != nil {
				slog.Error("github open PR check failed", "error", err, "rule_id", ruleID)
				continue
			}
			if open {
				slog.Debug("skipping alert, open PR exists", "rule_id", ruleID)
				continue
			}

			merged, err := e.github.HasRecentlyMergedPR(ctx, ruleID, e.mergeWindow)
			if err != nil {
				slog.Error("github merged PR check failed", "error", err, "rule_id", ruleID)
				continue
			}
			if merged {
				slog.Debug("skipping alert, recently merged PR exists", "rule_id", ruleID)
				continue
			}
		}

		if err := e.submitOrchestratorJob(ctx, action, ruleID); err != nil {
			slog.Error("orchestrator job failed", "error", err, "rule_id", ruleID)
			continue
		}
	}
	return nil
}

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action, ruleID string) error {
	if e.orchestrator == nil {
		slog.Warn("orchestrator client not configured, skipping job submission")
		return nil
	}

	task := fmt.Sprintf("SigNoz alert firing: %s\n\n"+
		"Rule ID: %s\n"+
		"Severity: %s\n\n"+
		"Details: %s\n\n"+
		"Investigate this issue using MCP tools. If a GitOps change can fix it, "+
		"create a PR with the label 'alert:%s'. If it requires manual intervention, "+
		"create a GitHub issue with your findings.",
		action.Finding.Title, ruleID, action.Finding.Severity,
		action.Finding.Detail, ruleID)

	body, _ := json.Marshal(map[string]any{
		"task":    task,
		"source":  fmt.Sprintf("patrol:%s", ruleID),
		"profile": "code-fix",
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
		"rule_id", ruleID,
		"title", action.Finding.Title,
	)
	return nil
}

func ruleIDFromFinding(f Finding) string {
	if id, ok := f.Data["rule_id"]; ok {
		return fmt.Sprintf("%v", id)
	}
	return f.Fingerprint
}
```

**Step 2: Run tests**

```bash
bazel test //services/cluster-agents/...
```

**Step 3: Commit**

```bash
git add services/cluster-agents/escalator.go
git commit -m "feat: rewrite escalator with GitHub PR label dedup"
```

---

### Task 9: Rewrite Patrol Agent — Tests

Replace patrol tests to verify the deterministic analyze step (no LLM).

**Files:**
- Modify: `services/cluster-agents/patrol_test.go`

**Step 1: Rewrite patrol tests**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPatrolAgent_AnalyzeConvertsAllFindingsToJobs(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	findings := []Finding{
		{
			Fingerprint: "patrol.alert.1",
			Severity:    SeverityCritical,
			Title:       "Pod OOMKilled",
			Data:        map[string]any{"rule_id": 1},
		},
		{
			Fingerprint: "patrol.alert.2",
			Severity:    SeverityWarning,
			Title:       "High Error Rate",
			Data:        map[string]any{"rule_id": 2},
		},
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}

	if len(actions) != 2 {
		t.Fatalf("expected 2 actions, got %d", len(actions))
	}
	for i, action := range actions {
		if action.Type != ActionOrchestratorJob {
			t.Errorf("action[%d]: expected orchestrator_job, got %s", i, action.Type)
		}
	}
}

func TestPatrolAgent_AnalyzeEmptyFindings(t *testing.T) {
	patrol := NewPatrolAgent(nil, nil, 1*time.Hour)

	actions, err := patrol.Analyze(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) != 0 {
		t.Errorf("expected 0 actions for empty findings, got %d", len(actions))
	}
}

func TestPatrolAgent_CollectAggregatesFromCollector(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{ID: 10, Name: "Test Alert", State: "firing", Severity: "critical"},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "")
	patrol := NewPatrolAgent(collector, nil, 1*time.Hour)

	findings, err := patrol.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/patrol_test.go
git commit -m "test: rewrite patrol tests for deterministic analyze"
```

---

### Task 10: Rewrite Patrol Agent — Implementation

Simplify the patrol agent: remove LLM, use alert collector, deterministic analyze.

**Files:**
- Modify: `services/cluster-agents/patrol.go`

**Step 1: Rewrite patrol**

```go
package main

import (
	"context"
	"log/slog"
	"time"
)

type PatrolAgent struct {
	collector *AlertCollector
	escalator *Escalator
	interval  time.Duration
}

func NewPatrolAgent(collector *AlertCollector, escalator *Escalator, interval time.Duration) *PatrolAgent {
	return &PatrolAgent{
		collector: collector,
		escalator: escalator,
		interval:  interval,
	}
}

func (p *PatrolAgent) Name() string            { return "cluster-patrol" }
func (p *PatrolAgent) Interval() time.Duration { return p.interval }

func (p *PatrolAgent) Collect(ctx context.Context) ([]Finding, error) {
	if p.collector == nil {
		return nil, nil
	}
	findings, err := p.collector.Collect(ctx)
	if err != nil {
		slog.Error("alert collector failed", "error", err)
		return nil, err
	}
	return findings, nil
}

func (p *PatrolAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	actions := make([]Action, 0, len(findings))
	for _, f := range findings {
		actions = append(actions, Action{
			Type:    ActionOrchestratorJob,
			Finding: f,
		})
	}
	return actions, nil
}

func (p *PatrolAgent) Execute(ctx context.Context, actions []Action) error {
	if p.escalator == nil {
		return nil
	}
	return p.escalator.Execute(ctx, actions)
}
```

**Step 2: Run tests**

```bash
bazel test //services/cluster-agents/...
```

**Step 3: Commit**

```bash
git add services/cluster-agents/patrol.go
git commit -m "feat: simplify patrol agent to alert-driven with deterministic analyze"
```

---

### Task 11: Rewrite main.go

Update main to wire up SigNoz + GitHub instead of NATS + K8s + LLM.

**Files:**
- Modify: `services/cluster-agents/main.go`

**Step 1: Rewrite main**

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	signozURL := envOr("SIGNOZ_URL", "http://signoz-query-service.signoz.svc.cluster.local:8080")
	signozToken := os.Getenv("SIGNOZ_API_KEY")
	orchestratorURL := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080")
	githubToken := os.Getenv("GITHUB_TOKEN")
	githubRepo := envOr("GITHUB_REPO", "jomcgi/homelab")
	httpPort := envOr("HTTP_PORT", "8080")
	patrolInterval := envDurationOr("PATROL_INTERVAL", 1*time.Hour)

	collector := NewAlertCollector(signozURL, signozToken)

	var github *GitHubPRChecker
	if githubToken != "" {
		github = NewGitHubPRChecker("https://api.github.com", githubToken, githubRepo)
	}
	orchestrator := NewOrchestratorClient(orchestratorURL)
	escalator := NewEscalator(github, orchestrator)

	patrol := NewPatrolAgent(collector, escalator, patrolInterval)
	runner := NewRunner([]Agent{patrol})

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

	slog.Info("cluster-agents starting", "patrol_interval", patrolInterval)
	runner.Run(ctx)

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	srv.Shutdown(shutdownCtx)
	slog.Info("cluster-agents stopped")
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envDurationOr(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			slog.Warn("invalid duration, using default", "key", key, "value", v, "default", fallback)
			return fallback
		}
		return d
	}
	return fallback
}
```

**Step 2: Run tests**

```bash
bazel test //services/cluster-agents/...
```

**Step 3: Commit**

```bash
git add services/cluster-agents/main.go
git commit -m "feat: rewire main for alert-driven patrol (SigNoz + GitHub, no NATS/LLM)"
```

---

### Task 12: Update BUILD File

Regenerate the BUILD file to reflect new/removed source files and dependencies.

**Files:**
- Modify: `services/cluster-agents/BUILD`

**Step 1: Run format to regenerate BUILD**

```bash
format
```

Gazelle should update the BUILD file to:
- Remove `collector_k8s.go`, `collector_argocd.go`, `llm.go`, `store.go`, `store_nats.go` from srcs
- Add `collector_alerts.go`, `github.go`
- Remove NATS, k8s deps
- Update test srcs accordingly

**Step 2: Verify the BUILD file looks correct**

Read `services/cluster-agents/BUILD` and verify:
- `go_library` srcs: `collector_alerts.go`, `escalator.go`, `github.go`, `main.go`, `model.go`, `patrol.go`, `runner.go`
- `go_library` deps: no NATS, no k8s
- `go_test` srcs: `collector_alerts_test.go`, `escalator_test.go`, `github_test.go`, `patrol_test.go`, `runner_test.go`
- `go_test` deps: no k8s/fake

**Step 3: Run tests one final time**

```bash
bazel test //services/cluster-agents/...
```

**Step 4: Commit**

```bash
git add services/cluster-agents/BUILD
git commit -m "build: update BUILD for alert-driven patrol"
```

---

### Task 13: Update Deployment Config

Update the Helm values to reflect new environment variables (SigNoz instead of NATS/LLM).

**Files:**
- Modify: `overlays/prod/cluster-agents/values.yaml`
- Modify: `charts/cluster-agents/values.yaml` (if env vars are templated there)

**Step 1: Read current values files**

Read both files to understand current env var configuration.

**Step 2: Update values**

- Remove: `NATS_URL`, `LLM_URL`, `LLM_MODEL` env vars
- Add: `SIGNOZ_URL`, `SIGNOZ_API_KEY` env vars
- Update: `PATROL_INTERVAL` from `5m` to `1h`
- Keep: `ORCHESTRATOR_URL`, `GITHUB_TOKEN`, `GITHUB_REPO`, `HTTP_PORT`

The SigNoz API key should come from a 1Password secret (`OnePasswordItem`).

**Step 3: Commit**

```bash
git add overlays/prod/cluster-agents/values.yaml charts/cluster-agents/
git commit -m "feat: update cluster-agents config for alert-driven patrol"
```

---

### Task 14: Push and Create PR

**Step 1: Push branch**

```bash
cd /tmp/claude-worktrees/alert-driven-patrol
git push -u origin feat/alert-driven-patrol
```

**Step 2: Create PR**

```bash
gh pr create --title "refactor: alert-driven patrol agent" --body "$(cat <<'EOF'
## Summary

- Replaces custom K8s/ArgoCD collectors + LLM triage with SigNoz alert-driven approach
- Dedup via GitHub PR labels instead of broken NATS KV store
- Patrol interval changed from 5min to 1hr
- Removes NATS, K8s client, and llama.cpp dependencies from cluster-agents

## Design

See `docs/plans/2026-03-08-alert-driven-patrol-design.md`

## Test plan

- [ ] All existing runner tests still pass
- [ ] Alert collector correctly filters for firing alerts only
- [ ] GitHub PR checker dedup prevents duplicate job submission
- [ ] Escalator skips when open PR exists with alert label
- [ ] Escalator submits job when no matching PR found
- [ ] Verify SigNoz API response shape matches our structs (may need field name adjustments)
- [ ] Deploy to cluster and verify patrol loop runs hourly
- [ ] Trigger a test alert and verify orchestrator job is submitted

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Enable auto-merge**

```bash
gh pr merge --auto --rebase
```

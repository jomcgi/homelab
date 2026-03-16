# Simplify Cluster Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify cluster agent task prompts to clear goals (not instructions) and remove the dead `profile` field, letting the deep planner decide the approach.

**Architecture:** Remove `profile` from the submit API, simplify escalator to require `Payload["task"]`, rewrite each agent's `Analyze()` with goal-style prompts, and clean up PRFixAgent's duplicate dedup logic.

**Tech Stack:** Go, Helm (chart version bump)

---

### Task 1: Remove `Profile` from orchestrator `SubmitRequest`

**Files:**

- Modify: `projects/agent_platform/orchestrator/model.go:60-66`
- Modify: `projects/agent_platform/orchestrator/api.go:82`
- Modify: `projects/agent_platform/orchestrator/api_test.go:117-172`

**Step 1: Remove `Profile` from `SubmitRequest`**

In `model.go`, delete the `Profile` field from `SubmitRequest` (line 62). Keep it in `JobRecord` (line 20) for backwards compat with existing KV entries.

```go
// SubmitRequest is the JSON body for POST /jobs.
type SubmitRequest struct {
	Task       string   `json:"task"`
	MaxRetries *int     `json:"max_retries,omitempty"`
	Source     string   `json:"source,omitempty"`
	Tags       []string `json:"tags,omitempty"`
}
```

**Step 2: Remove profile assignment in `api.go`**

In `api.go` line 82, remove `Profile: req.Profile,` from the `JobRecord` construction.

**Step 3: Update tests**

In `api_test.go`:

- Delete `TestHandleSubmit_WithProfile` (lines 117-146) entirely — this tests dead functionality.
- In `TestHandleSubmit_NoProfile` (lines 148-172): remove the profile assertion (lines 171-172) and rename the test to just `TestHandleSubmit`.

**Step 4: Verify build**

Run: `cd projects/agent_platform/orchestrator && go vet ./...`
Expected: no errors

**Step 5: Commit**

```
refactor(agent-orchestrator): remove profile from SubmitRequest

The profile field was stored but never used by the consumer or runner.
The deep planner decides the approach autonomously from the task description.
```

---

### Task 2: Simplify `escalator.go` — remove profile and patrol fallback

**Files:**

- Modify: `projects/agent_platform/cluster_agents/escalator.go:117-194`

**Step 1: Rewrite `submitOrchestratorJob`**

Replace the entire function body. Remove the patrol-style fallback prompt builder (`if task == ""` block, lines 127-143) and the profile extraction (lines 160-162). All agents must now provide `Payload["task"]`.

```go
func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action, tag string) error {
	if e.orchestrator == nil {
		slog.Warn("orchestrator client not configured, skipping job submission")
		return nil
	}

	task, _ := action.Payload["task"].(string)
	if task == "" {
		return fmt.Errorf("action payload missing task")
	}

	source := action.Finding.Source
	if source == "" {
		source = action.Finding.Fingerprint
	}

	tags := []string{tag}
	if sha, ok := action.Finding.Data["latest_sha"].(string); ok && sha != "" {
		tags = append(tags, "sha:"+sha)
	}

	jobReq := map[string]any{
		"task":   task,
		"source": source,
		"tags":   tags,
	}

	body, _ := json.Marshal(jobReq)

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
		"title", action.Finding.Title,
		"tag", tag,
	)
	return nil
}
```

**Step 2: Delete `ruleIDFromFinding` helper**

Delete the `ruleIDFromFinding` function (lines 189-194) — no longer needed after removing the patrol fallback. The tag logic in `Execute` already handles `rule_id` extraction (lines 60-63).

**Step 3: Verify build**

Run: `cd projects/agent_platform/cluster_agents && go vet ./...`
Expected: no errors

**Step 4: Commit**

```
refactor(cluster-agents): simplify escalator, require task in payload

Remove the patrol-style backwards-compat prompt builder and profile
field from job submissions. All agents now provide their own task string.
```

---

### Task 3: Add task prompt to `PatrolAgent.Analyze()`

**Files:**

- Modify: `projects/agent_platform/cluster_agents/patrol.go:38-51`

**Step 1: Rewrite `Analyze` to build goal-style task and set `Payload["task"]`**

```go
func (p *PatrolAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	actions := make([]Action, 0, len(findings))
	for _, f := range findings {
		ruleID := f.Fingerprint
		if id, ok := f.Data["rule_id"]; ok {
			ruleID = fmt.Sprintf("%v", id)
		}

		task := fmt.Sprintf("SigNoz alert %q is firing (severity: %s, rule: %s).\n\n"+
			"Investigate the root cause. If a GitOps change can fix it, create and merge a PR.\n"+
			"If it requires manual intervention, create a GitHub issue with your findings.\n\n"+
			"Details: %s",
			f.Title, f.Severity, ruleID, f.Detail)

		actions = append(actions, Action{
			Type:    ActionOrchestratorJob,
			Finding: f,
			Payload: map[string]any{"task": task},
		})
	}
	return actions, nil
}
```

**Step 2: Add `"fmt"` to imports**

The patrol.go imports need `"fmt"` added.

**Step 3: Verify build**

Run: `cd projects/agent_platform/cluster_agents && go vet ./...`
Expected: no errors

**Step 4: Commit**

```
refactor(cluster-agents): add goal-style task prompt to PatrolAgent
```

---

### Task 4: Simplify improvement agent task prompts

**Files:**

- Modify: `projects/agent_platform/cluster_agents/test_coverage_agent.go:52-79`
- Modify: `projects/agent_platform/cluster_agents/readme_freshness_agent.go:52-83`
- Modify: `projects/agent_platform/cluster_agents/rules_agent.go:52-87`

**Step 1: Rewrite `TestCoverageAgent.Analyze()`**

```go
func (a *TestCoverageAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	commitRange, _ := findings[0].Data["commit_range"].(string)

	task := fmt.Sprintf("New commits landed on main (%s). Review changed Go and Python "+
		"files that lack test coverage and create PRs adding tests.\n\n"+
		"One PR per project, monitored and auto-merged.", commitRange)

	return []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: findings[0],
			Payload: map[string]any{"task": task},
		},
	}, nil
}
```

**Step 2: Rewrite `ReadmeFreshnessAgent.Analyze()`**

```go
func (a *ReadmeFreshnessAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	task := "New commits landed on main. Audit all projects/*/README.md files for accuracy " +
		"against the actual project structure, configs, and code.\n\n" +
		"Fix any inaccuracies. One PR per project, monitored and auto-merged."

	return []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: findings[0],
			Payload: map[string]any{"task": task},
		},
	}, nil
}
```

**Step 3: Rewrite `RulesAgent.Analyze()`**

```go
func (a *RulesAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	commitRange, _ := findings[0].Data["commit_range"].(string)

	task := fmt.Sprintf("New commits landed on main (%s). Review merged PRs for patterns "+
		"that could be caught statically (semgrep rules) or prevented by Claude hooks.\n\n"+
		"One PR per rule or config change, monitored and auto-merged.", commitRange)

	return []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: findings[0],
			Payload: map[string]any{"task": task},
		},
	}, nil
}
```

**Step 4: Verify build**

Run: `cd projects/agent_platform/cluster_agents && go vet ./...`
Expected: no errors

**Step 5: Commit**

```
refactor(cluster-agents): simplify improvement agent task prompts

Replace verbose instruction-style prompts with clear goal descriptions.
The deep planner decides the approach using recipes on disk.
```

---

### Task 5: Simplify `PRFixAgent` — remove duplicate dedup, simplify prompt

**Files:**

- Modify: `projects/agent_platform/cluster_agents/pr_fix_agent.go:13-141`
- Modify: `projects/agent_platform/cluster_agents/main.go:55`

**Step 1: Remove `orchestrator` field and `hasActiveJob` from PRFixAgent**

The escalator already handles dedup via `hasActiveJob`. Remove:

- The `orchestrator *OrchestratorClient` field from the struct (line 15)
- The `orchestrator` parameter from `NewPRFixAgent` (line 21)
- The entire `hasActiveJob` method (lines 73-101)
- The dedup logic in `Collect` (lines 44-55) — just emit all findings, let escalator dedup

New struct and constructor:

```go
type PRFixAgent struct {
	github         *GitHubClient
	escalator      *Escalator
	interval       time.Duration
	staleThreshold time.Duration
}

func NewPRFixAgent(github *GitHubClient, escalator *Escalator, interval, staleThreshold time.Duration) *PRFixAgent {
	return &PRFixAgent{
		github:         github,
		escalator:      escalator,
		interval:       interval,
		staleThreshold: staleThreshold,
	}
}
```

New `Collect`:

```go
func (a *PRFixAgent) Collect(ctx context.Context) ([]Finding, error) {
	prs, err := a.github.OpenPRsWithFailingChecks(ctx, a.staleThreshold)
	if err != nil {
		return nil, fmt.Errorf("fetching failing PRs: %w", err)
	}

	var findings []Finding
	for _, pr := range prs {
		findings = append(findings, Finding{
			Fingerprint: fmt.Sprintf("improvement:pr-fix:%d", pr.Number),
			Source:      "improvement:pr-fix",
			Severity:    SeverityInfo,
			Title:       fmt.Sprintf("PR #%d has failing CI checks", pr.Number),
			Data: map[string]any{
				"pr_number": pr.Number,
				"branch":    pr.Head.Ref,
			},
			Timestamp: time.Now(),
		})
	}

	return findings, nil
}
```

**Step 2: Rewrite `Analyze` with goal-style prompt**

```go
func (a *PRFixAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	var actions []Action
	for _, f := range findings {
		prNumber, _ := f.Data["pr_number"].(int)
		branch, _ := f.Data["branch"].(string)

		task := fmt.Sprintf("PR #%d on branch %s has failing CI checks.\n\n"+
			"Diagnose and fix the CI failure. Push the fix (no force push).",
			prNumber, branch)

		actions = append(actions, Action{
			Type:    ActionOrchestratorJob,
			Finding: f,
			Payload: map[string]any{"task": task},
		})
	}

	return actions, nil
}
```

**Step 3: Remove unused imports**

Remove `"encoding/json"`, `"log/slog"`, `"net/http"`, `"net/url"` from pr_fix_agent.go imports — only `"context"`, `"fmt"`, `"time"` remain.

**Step 4: Update `main.go` constructor call**

In `main.go` line 55, remove the `orchestrator` argument:

```go
NewPRFixAgent(githubClient, escalator, prFixInterval, prFixStaleThreshold),
```

**Step 5: Verify build**

Run: `cd projects/agent_platform/cluster_agents && go vet ./...`
Expected: no errors

**Step 6: Commit**

```
refactor(cluster-agents): simplify PRFixAgent, remove duplicate dedup

Remove PRFixAgent's own hasActiveJob — the escalator already handles
dedup. Simplify task prompt to a clear goal.
```

---

### Task 6: Bump chart version

**Files:**

- Modify: `projects/agent_platform/cluster_agents/deploy/Chart.yaml:5`
- Modify: `projects/agent_platform/cluster_agents/deploy/application.yaml:11`

**Step 1: Bump version in both files**

Chart.yaml: `version: 0.3.7` → `version: 0.4.0` (minor bump — behavioural change in prompts)

application.yaml: `targetRevision: 0.3.7` → `targetRevision: 0.4.0`

**Step 2: Commit**

```
chore(cluster-agents): bump chart version to 0.4.0
```

---

### Task 7: Run format and push

**Step 1: Run format**

Run: `format` (in the worktree)
This updates BUILD files and formats Go code.

**Step 2: Commit formatting if needed**

```
style: auto-format
```

**Step 3: Push and create PR**

```bash
git push -u origin feat/simplify-cluster-agents
gh pr create --title "refactor(cluster-agents): simplify task prompts for deep-plan orchestrator" --body "..."
```

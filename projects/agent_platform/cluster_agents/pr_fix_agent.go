package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"time"
)

type PRFixAgent struct {
	github         *GitHubClient
	orchestrator   *OrchestratorClient
	escalator      *Escalator
	interval       time.Duration
	staleThreshold time.Duration
}

func NewPRFixAgent(github *GitHubClient, orchestrator *OrchestratorClient, escalator *Escalator, interval, staleThreshold time.Duration) *PRFixAgent {
	return &PRFixAgent{
		github:         github,
		orchestrator:   orchestrator,
		escalator:      escalator,
		interval:       interval,
		staleThreshold: staleThreshold,
	}
}

func (a *PRFixAgent) Name() string            { return "pr-fix" }
func (a *PRFixAgent) Interval() time.Duration { return a.interval }

func (a *PRFixAgent) Collect(ctx context.Context) ([]Finding, error) {
	prs, err := a.github.OpenPRsWithFailingChecks(ctx, a.staleThreshold)
	if err != nil {
		return nil, fmt.Errorf("fetching failing PRs: %w", err)
	}

	var findings []Finding
	for _, pr := range prs {
		tag := fmt.Sprintf("improvement:pr-fix:%d", pr.Number)

		active, err := a.hasActiveJob(ctx, tag)
		if err != nil {
			slog.Warn("dedup check failed for PR, skipping",
				"pr", pr.Number,
				"error", err,
			)
			continue
		}
		if active {
			slog.Info("skipping PR with active fix job", "pr", pr.Number)
			continue
		}

		findings = append(findings, Finding{
			Fingerprint: tag,
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

func (a *PRFixAgent) hasActiveJob(ctx context.Context, tag string) (bool, error) {
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
		return false, fmt.Errorf("orchestrator list jobs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	var result orchestratorListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("decode orchestrator response: %w", err)
	}

	return result.Total > 0, nil
}

func (a *PRFixAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	var actions []Action
	for _, f := range findings {
		prNumber, _ := f.Data["pr_number"].(int)
		branch, _ := f.Data["branch"].(string)

		task := fmt.Sprintf(`PR #%d has failing CI checks on branch %s.

1. Check out the branch
2. Use BuildBuddy MCP tools to understand the CI failure
3. Fix the issue
4. Commit and push (do NOT force push)

Before starting:
- Run `+"`gh pr view %d --json commits,body`"+` to understand context
- Check PR comments for any human instructions or "do not auto-fix" labels

Use conventional commit format:
fix(<scope>): resolve CI failure in PR #%d`, prNumber, branch, prNumber, prNumber)

		actions = append(actions, Action{
			Type:    ActionOrchestratorJob,
			Finding: f,
			Payload: map[string]any{
				"task":    task,
				"profile": "ci-debug",
			},
		})
	}

	return actions, nil
}

func (a *PRFixAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

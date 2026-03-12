package main

import (
	"context"
	"fmt"
	"time"
)

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

func (a *PRFixAgent) Name() string            { return "pr-fix" }
func (a *PRFixAgent) Interval() time.Duration { return a.interval }

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

func (a *PRFixAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

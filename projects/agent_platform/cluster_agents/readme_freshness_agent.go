package main

import (
	"context"
	"fmt"
	"time"
)

const readmeFreshnessTag = "improvement:readme-freshness"

type ReadmeFreshnessAgent struct {
	gate     *GitActivityGate
	interval time.Duration
}

func NewReadmeFreshnessAgent(gate *GitActivityGate, interval time.Duration) *ReadmeFreshnessAgent {
	return &ReadmeFreshnessAgent{
		gate:     gate,
		interval: interval,
	}
}

func (a *ReadmeFreshnessAgent) Name() string            { return "readme-freshness" }
func (a *ReadmeFreshnessAgent) Interval() time.Duration { return a.interval }

func (a *ReadmeFreshnessAgent) Collect(ctx context.Context) ([]Finding, error) {
	commitRange, hasActivity, err := a.gate.Check(ctx, readmeFreshnessTag)
	if err != nil {
		return nil, fmt.Errorf("git activity check: %w", err)
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{
		{
			Fingerprint: readmeFreshnessTag,
			Source:      readmeFreshnessTag,
			Severity:    SeverityInfo,
			Title:       "README freshness check",
			Data: map[string]any{
				"commit_range": commitRange,
			},
			Timestamp: time.Now(),
		},
	}, nil
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

	return []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: findings[0],
			Payload: map[string]any{
				"task": task,
			},
		},
	}, nil
}

func (a *ReadmeFreshnessAgent) Execute(_ context.Context, _ []Action) error {
	return nil
}

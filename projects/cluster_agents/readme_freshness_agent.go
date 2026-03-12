package main

import (
	"context"
	"fmt"
	"time"
)

const readmeFreshnessTag = "improvement:readme-freshness"

type ReadmeFreshnessAgent struct {
	gate      *GitActivityGate
	escalator *Escalator
	interval  time.Duration
}

func NewReadmeFreshnessAgent(gate *GitActivityGate, escalator *Escalator, interval time.Duration) *ReadmeFreshnessAgent {
	return &ReadmeFreshnessAgent{
		gate:      gate,
		escalator: escalator,
		interval:  interval,
	}
}

func (a *ReadmeFreshnessAgent) Name() string            { return "readme-freshness" }
func (a *ReadmeFreshnessAgent) Interval() time.Duration { return a.interval }

func (a *ReadmeFreshnessAgent) Collect(ctx context.Context) ([]Finding, error) {
	latestSHA, commitRange, hasActivity, err := a.gate.Check(ctx, readmeFreshnessTag)
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
				"latest_sha":   latestSHA,
			},
			Timestamp: time.Now(),
		},
	}, nil
}

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

func (a *ReadmeFreshnessAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

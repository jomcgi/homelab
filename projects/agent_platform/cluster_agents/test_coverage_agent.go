package main

import (
	"context"
	"fmt"
	"time"
)

const testCoverageTag = "improvement:test-coverage"

type TestCoverageAgent struct {
	gate      *GitActivityGate
	escalator *Escalator
	interval  time.Duration
}

func NewTestCoverageAgent(gate *GitActivityGate, escalator *Escalator, interval time.Duration) *TestCoverageAgent {
	return &TestCoverageAgent{
		gate:      gate,
		escalator: escalator,
		interval:  interval,
	}
}

func (a *TestCoverageAgent) Name() string            { return "test-coverage" }
func (a *TestCoverageAgent) Interval() time.Duration { return a.interval }

func (a *TestCoverageAgent) Collect(ctx context.Context) ([]Finding, error) {
	latestSHA, commitRange, hasActivity, err := a.gate.Check(ctx, testCoverageTag)
	if err != nil {
		return nil, fmt.Errorf("git activity check: %w", err)
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{
		{
			Fingerprint: testCoverageTag,
			Source:      testCoverageTag,
			Severity:    SeverityInfo,
			Title:       "Test coverage improvement opportunity",
			Data: map[string]any{
				"commit_range": commitRange,
				"latest_sha":   latestSHA,
			},
			Timestamp: time.Now(),
		},
	}, nil
}

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

func (a *TestCoverageAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

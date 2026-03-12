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
	commitRange, hasActivity, err := a.gate.Check(ctx, testCoverageTag)
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

	task := fmt.Sprintf(`Review files changed in commits %s on main. For each Go or Python source file that was modified and lacks a corresponding _test file, write tests that cover the key behaviors.

Before starting:
- Check `+"`gh pr list --search \"test\"`"+` for existing test coverage PRs
- Check `+"`gh issue list --search \"test\"`"+` for related issues
- Skip files in generated code (zz_generated.*, *_types.go deepcopy)

Create one PR per project. Use conventional commit format:
test(<project>): add coverage for <description>`, commitRange)

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

func (a *TestCoverageAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

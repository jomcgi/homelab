package main

import (
	"context"
	"fmt"
	"time"
)

const rulesTag = "improvement:rules"

type RulesAgent struct {
	gate      *GitActivityGate
	escalator *Escalator
	interval  time.Duration
}

func NewRulesAgent(gate *GitActivityGate, escalator *Escalator, interval time.Duration) *RulesAgent {
	return &RulesAgent{
		gate:      gate,
		escalator: escalator,
		interval:  interval,
	}
}

func (a *RulesAgent) Name() string            { return "rules" }
func (a *RulesAgent) Interval() time.Duration { return a.interval }

func (a *RulesAgent) Collect(ctx context.Context) ([]Finding, error) {
	latestSHA, commitRange, hasActivity, err := a.gate.Check(ctx, rulesTag)
	if err != nil {
		return nil, fmt.Errorf("git activity check: %w", err)
	}
	if !hasActivity {
		return nil, nil
	}

	return []Finding{
		{
			Fingerprint: rulesTag,
			Source:      rulesTag,
			Severity:    SeverityInfo,
			Title:       "Rules improvement opportunity",
			Data: map[string]any{
				"commit_range": commitRange,
				"latest_sha":   latestSHA,
			},
			Timestamp: time.Now(),
		},
	}, nil
}

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

func (a *RulesAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

package main

import (
	"context"
	"fmt"
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

func (p *PatrolAgent) Execute(ctx context.Context, actions []Action) error {
	if p.escalator == nil {
		return nil
	}
	return p.escalator.Execute(ctx, actions)
}

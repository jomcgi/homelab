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
	commitRange, hasActivity, err := a.gate.Check(ctx, rulesTag)
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

	task := fmt.Sprintf(`Review PRs merged to main in commits %s. For each merged PR:

1. If it's a bug fix (fix: prefix), analyze the diff for patterns that could
   be caught statically. Propose a semgrep rule in bazel/semgrep/rules/ with
   a test case. Check existing rules to avoid duplicates.

2. If it reveals an agent anti-pattern or a common mistake, propose additions
   to .claude/CLAUDE.md or .claude/settings.json hooks to prevent recurrence.

Before starting:
- Check `+"`gh pr list --search \"semgrep OR rule OR hook\"`"+` for existing work
- Check `+"`gh issue list`"+` for related issues
- Review existing rules in bazel/semgrep/rules/ and .claude/settings.json

Create one PR per rule/config change. Use conventional commit format:
- build(semgrep): add rule for <pattern>
- ci(claude): add hook to prevent <behavior>`, commitRange)

	return []Action{
		{
			Type:    ActionOrchestratorJob,
			Finding: findings[0],
			Payload: map[string]any{
				"task":    task,
				"profile": "code-fix",
			},
		},
	}, nil
}

func (a *RulesAgent) Execute(ctx context.Context, actions []Action) error {
	return a.escalator.Execute(ctx, actions)
}

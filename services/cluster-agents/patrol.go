package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"
)

const patrolSystemPrompt = `You are a Kubernetes cluster health analyzer. You receive structured findings from cluster monitoring and must classify them into actions.

For each finding, decide the appropriate action:
- "log" — informational, no action needed (normal churn, expected behavior)
- "github_issue" — warning that should be tracked but doesn't need immediate automated remediation
- "orchestrator_job" — critical issue that an AI agent should investigate and attempt to fix

Respond with a JSON array of action objects:
[{"action_type": "log|github_issue|orchestrator_job", "finding_fingerprint": "...", "severity": "info|warning|critical", "reasoning": "brief explanation"}]

Consider correlations between findings. Multiple related issues may indicate a root cause worth escalating even if individual findings seem minor.

IMPORTANT: Be conservative with orchestrator_job — only use it for issues that are clearly actionable and fixable via GitOps changes or known remediation steps. Do not escalate transient issues.`

type PatrolAgent struct {
	collectors []collector
	llm        *LLMClient
	escalator  *Escalator
	interval   time.Duration
}

type collector interface {
	Collect(ctx context.Context) ([]Finding, error)
}

type llmAction struct {
	ActionType         string `json:"action_type"`
	FindingFingerprint string `json:"finding_fingerprint"`
	Severity           string `json:"severity"`
	Reasoning          string `json:"reasoning"`
}

func NewPatrolAgent(collectors []collector, llm *LLMClient, escalator *Escalator, interval time.Duration) *PatrolAgent {
	return &PatrolAgent{
		collectors: collectors,
		llm:        llm,
		escalator:  escalator,
		interval:   interval,
	}
}

func (p *PatrolAgent) Name() string            { return "cluster-patrol" }
func (p *PatrolAgent) Interval() time.Duration { return p.interval }

func (p *PatrolAgent) Collect(ctx context.Context) ([]Finding, error) {
	var all []Finding
	for _, c := range p.collectors {
		findings, err := c.Collect(ctx)
		if err != nil {
			slog.Error("collector failed", "error", err)
			continue
		}
		all = append(all, findings...)
	}
	return all, nil
}

func (p *PatrolAgent) Analyze(ctx context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	findingsJSON, err := json.Marshal(findings)
	if err != nil {
		return nil, fmt.Errorf("marshal findings: %w", err)
	}

	response, err := p.llm.Complete(ctx, patrolSystemPrompt, string(findingsJSON))
	if err != nil {
		return nil, fmt.Errorf("llm analysis: %w", err)
	}

	var llmActions []llmAction
	if err := json.Unmarshal([]byte(response), &llmActions); err != nil {
		slog.Error("failed to parse LLM response", "response", response, "error", err)
		return nil, fmt.Errorf("parse llm response: %w", err)
	}

	findingMap := make(map[string]Finding, len(findings))
	for _, f := range findings {
		findingMap[f.Fingerprint] = f
	}

	var actions []Action
	for _, la := range llmActions {
		finding, ok := findingMap[la.FindingFingerprint]
		if !ok {
			slog.Warn("LLM referenced unknown fingerprint", "fingerprint", la.FindingFingerprint)
			continue
		}

		var actionType ActionType
		switch la.ActionType {
		case "log":
			actionType = ActionLog
		case "github_issue":
			actionType = ActionGitHubIssue
		case "orchestrator_job":
			actionType = ActionOrchestratorJob
		default:
			slog.Warn("unknown action type from LLM", "type", la.ActionType)
			continue
		}

		actions = append(actions, Action{
			Type:    actionType,
			Finding: finding,
			Payload: map[string]any{"reasoning": la.Reasoning},
		})
	}

	return actions, nil
}

func (p *PatrolAgent) Execute(ctx context.Context, actions []Action) error {
	return p.escalator.Execute(ctx, actions)
}

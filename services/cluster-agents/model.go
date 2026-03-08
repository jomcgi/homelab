package main

import (
	"context"
	"time"
)

// Severity levels for findings.
type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

// ActionType determines escalation path.
type ActionType string

const (
	ActionLog             ActionType = "log"
	ActionGitHubIssue     ActionType = "github_issue"
	ActionOrchestratorJob ActionType = "orchestrator_job"
)

// Finding represents a single observation from a collector.
type Finding struct {
	Fingerprint string         `json:"fingerprint"`
	Source      string         `json:"source"`
	Severity    Severity       `json:"severity"`
	Title       string         `json:"title"`
	Detail      string         `json:"detail"`
	Data        map[string]any `json:"data,omitempty"`
	Timestamp   time.Time      `json:"timestamp"`
}

// Action represents an escalation decision from the analyzer.
type Action struct {
	Type    ActionType     `json:"type"`
	Finding Finding        `json:"finding"`
	Payload map[string]any `json:"payload,omitempty"`
}

// Agent defines the interface for autonomous agent loops.
type Agent interface {
	Name() string
	Collect(ctx context.Context) ([]Finding, error)
	Analyze(ctx context.Context, findings []Finding) ([]Action, error)
	Execute(ctx context.Context, actions []Action) error
	Interval() time.Duration
}

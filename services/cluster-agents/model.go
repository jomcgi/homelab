package main

import (
	"context"
	"time"
)

type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

type ActionType string

const (
	ActionLog             ActionType = "log"
	ActionOrchestratorJob ActionType = "orchestrator_job"
)

type Finding struct {
	Fingerprint string         `json:"fingerprint"`
	Source      string         `json:"source"`
	Severity    Severity       `json:"severity"`
	Title       string         `json:"title"`
	Detail      string         `json:"detail"`
	Data        map[string]any `json:"data,omitempty"`
	Timestamp   time.Time      `json:"timestamp"`
}

type Action struct {
	Type    ActionType     `json:"type"`
	Finding Finding        `json:"finding"`
	Payload map[string]any `json:"payload,omitempty"`
}

type Agent interface {
	Name() string
	Collect(ctx context.Context) ([]Finding, error)
	Analyze(ctx context.Context, findings []Finding) ([]Action, error)
	Execute(ctx context.Context, actions []Action) error
	Interval() time.Duration
}

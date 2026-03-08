package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

type OrchestratorClient struct {
	baseURL string
	client  *http.Client
}

func NewOrchestratorClient(baseURL string) *OrchestratorClient {
	return &OrchestratorClient{
		baseURL: baseURL,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

type Escalator struct {
	github       *GitHubPRChecker
	orchestrator *OrchestratorClient
	mergeWindow  time.Duration
}

func NewEscalator(github *GitHubPRChecker, orchestrator *OrchestratorClient) *Escalator {
	return &Escalator{
		github:       github,
		orchestrator: orchestrator,
		mergeWindow:  1 * time.Hour,
	}
}

func (e *Escalator) Execute(ctx context.Context, actions []Action) error {
	for _, action := range actions {
		if action.Type == ActionLog {
			slog.Info("finding",
				"severity", action.Finding.Severity,
				"title", action.Finding.Title,
				"detail", action.Finding.Detail,
				"fingerprint", action.Finding.Fingerprint,
			)
			continue
		}

		ruleID := ruleIDFromFinding(action.Finding)

		if e.github != nil {
			open, err := e.github.HasOpenPR(ctx, ruleID)
			if err != nil {
				slog.Error("github open PR check failed", "error", err, "rule_id", ruleID)
				continue
			}
			if open {
				slog.Debug("skipping alert, open PR exists", "rule_id", ruleID)
				continue
			}

			merged, err := e.github.HasRecentlyMergedPR(ctx, ruleID, e.mergeWindow)
			if err != nil {
				slog.Error("github merged PR check failed", "error", err, "rule_id", ruleID)
				continue
			}
			if merged {
				slog.Debug("skipping alert, recently merged PR exists", "rule_id", ruleID)
				continue
			}
		}

		if err := e.submitOrchestratorJob(ctx, action, ruleID); err != nil {
			slog.Error("orchestrator job failed", "error", err, "rule_id", ruleID)
			continue
		}
	}
	return nil
}

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action, ruleID string) error {
	if e.orchestrator == nil {
		slog.Warn("orchestrator client not configured, skipping job submission")
		return nil
	}

	task := fmt.Sprintf("SigNoz alert firing: %s\n\n"+
		"Rule ID: %s\n"+
		"Severity: %s\n\n"+
		"Details: %s\n\n"+
		"Investigate this issue using MCP tools. If a GitOps change can fix it, "+
		"create a PR with the label 'alert:%s'. If it requires manual intervention, "+
		"create a GitHub issue with your findings.",
		action.Finding.Title, ruleID, action.Finding.Severity,
		action.Finding.Detail, ruleID)

	body, _ := json.Marshal(map[string]any{
		"task":    task,
		"source":  fmt.Sprintf("patrol:%s", ruleID),
		"profile": "code-fix",
	})

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, e.orchestrator.baseURL+"/jobs", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.orchestrator.client.Do(req)
	if err != nil {
		return fmt.Errorf("submit job: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	slog.Info("submitted orchestrator job",
		"rule_id", ruleID,
		"title", action.Finding.Title,
	)
	return nil
}

func ruleIDFromFinding(f Finding) string {
	if id, ok := f.Data["rule_id"]; ok {
		return fmt.Sprintf("%v", id)
	}
	return f.Fingerprint
}

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

type GitHubClient struct {
	token  string
	repo   string
	client *http.Client
}

func NewGitHubClient(token, repo string) *GitHubClient {
	return &GitHubClient{
		token:  token,
		repo:   repo,
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

type Escalator struct {
	store        FindingsStore
	github       *GitHubClient
	orchestrator *OrchestratorClient
	findingTTL   time.Duration
}

func NewEscalator(store FindingsStore, github *GitHubClient, orchestrator *OrchestratorClient) *Escalator {
	return &Escalator{
		store:        store,
		github:       github,
		orchestrator: orchestrator,
		findingTTL:   24 * time.Hour,
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

		ok, err := e.store.ShouldEscalate(ctx, action.Finding.Fingerprint)
		if err != nil {
			slog.Error("dedup check failed", "error", err, "fingerprint", action.Finding.Fingerprint)
			continue
		}
		if !ok {
			slog.Debug("skipping duplicate finding", "fingerprint", action.Finding.Fingerprint)
			continue
		}

		switch action.Type {
		case ActionGitHubIssue:
			if err := e.createGitHubIssue(ctx, action); err != nil {
				slog.Error("github issue failed", "error", err)
				continue
			}
		case ActionOrchestratorJob:
			if err := e.submitOrchestratorJob(ctx, action); err != nil {
				slog.Error("orchestrator job failed", "error", err)
				continue
			}
		}

		e.store.MarkEscalated(ctx, action.Finding.Fingerprint, e.findingTTL)
	}
	return nil
}

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action) error {
	task := fmt.Sprintf("Cluster Patrol detected an issue that needs investigation and remediation.\n\n"+
		"**Issue:** %s\n\n"+
		"**Details:** %s\n\n"+
		"**Severity:** %s\n\n"+
		"Investigate this issue using MCP tools. If a GitOps change can fix it, create a PR. "+
		"If it requires manual intervention, create a GitHub issue with your findings.",
		action.Finding.Title, action.Finding.Detail, action.Finding.Severity)

	body, _ := json.Marshal(map[string]any{
		"task":   task,
		"source": "cluster-patrol",
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
		"fingerprint", action.Finding.Fingerprint,
		"title", action.Finding.Title,
	)
	return nil
}

func (e *Escalator) createGitHubIssue(ctx context.Context, action Action) error {
	if e.github == nil {
		slog.Warn("github client not configured, skipping issue creation")
		return nil
	}

	body, _ := json.Marshal(map[string]any{
		"title": fmt.Sprintf("[cluster-patrol] %s", action.Finding.Title),
		"body": fmt.Sprintf("## Cluster Patrol Finding\n\n"+
			"**Severity:** %s\n"+
			"**Source:** %s\n"+
			"**Fingerprint:** `%s`\n\n"+
			"### Details\n\n%s\n\n"+
			"---\n_Auto-created by cluster-patrol agent_",
			action.Finding.Severity, action.Finding.Source,
			action.Finding.Fingerprint, action.Finding.Detail),
		"labels": []string{"cluster-patrol", string(action.Finding.Severity)},
	})

	url := fmt.Sprintf("https://api.github.com/repos/%s/issues", e.github.repo)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+e.github.token)
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.github.client.Do(req)
	if err != nil {
		return fmt.Errorf("create issue: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("github returned %d", resp.StatusCode)
	}

	slog.Info("created github issue",
		"fingerprint", action.Finding.Fingerprint,
		"title", action.Finding.Title,
	)
	return nil
}

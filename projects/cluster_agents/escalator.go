package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
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

type orchestratorListResponse struct {
	Jobs  []orchestratorJob `json:"jobs"`
	Total int               `json:"total"`
}

type orchestratorJob struct {
	ID     string   `json:"id"`
	Status string   `json:"status"`
	Tags   []string `json:"tags,omitempty"`
}

type Escalator struct {
	orchestrator *OrchestratorClient
}

func NewEscalator(orchestrator *OrchestratorClient) *Escalator {
	return &Escalator{
		orchestrator: orchestrator,
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

		// Use fingerprint as tag for improvement agents, rule_id for patrol.
		tag := action.Finding.Fingerprint
		if ruleID, ok := action.Finding.Data["rule_id"]; ok {
			tag = fmt.Sprintf("alert:%v", ruleID)
		}

		exists, err := e.hasActiveJob(ctx, tag)
		if err != nil {
			slog.Error("dedup check failed", "error", err, "tag", tag)
			continue
		}
		if exists {
			slog.Info("skipping, active job exists", "tag", tag)
			continue
		}

		if err := e.submitOrchestratorJob(ctx, action, tag); err != nil {
			slog.Error("orchestrator job failed", "error", err, "tag", tag)
			continue
		}
	}
	return nil
}

func (e *Escalator) hasActiveJob(ctx context.Context, tag string) (bool, error) {
	if e.orchestrator == nil {
		return false, nil
	}

	u := fmt.Sprintf("%s/jobs?status=%s&tags=%s&limit=1",
		e.orchestrator.baseURL,
		url.QueryEscape("PENDING,RUNNING"),
		url.QueryEscape(tag),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return false, err
	}

	resp, err := e.orchestrator.client.Do(req)
	if err != nil {
		return false, fmt.Errorf("orchestrator list jobs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	var result orchestratorListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("decode orchestrator response: %w", err)
	}

	return result.Total > 0, nil
}

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action, tag string) error {
	if e.orchestrator == nil {
		slog.Warn("orchestrator client not configured, skipping job submission")
		return nil
	}

	task, _ := action.Payload["task"].(string)
	if task == "" {
		return fmt.Errorf("action payload missing task")
	}

	source := action.Finding.Source
	if source == "" {
		source = action.Finding.Fingerprint
	}

	tags := []string{tag}
	if sha, ok := action.Finding.Data["latest_sha"].(string); ok && sha != "" {
		tags = append(tags, "sha:"+sha)
	}

	jobReq := map[string]any{
		"task":   task,
		"source": source,
		"tags":   tags,
	}

	body, _ := json.Marshal(jobReq)

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
		"title", action.Finding.Title,
		"tag", tag,
	)
	return nil
}

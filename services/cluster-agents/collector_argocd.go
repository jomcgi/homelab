package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type ArgoCDAppList struct {
	Items []ArgoCDApp `json:"items"`
}

type ArgoCDApp struct {
	Metadata ArgoCDMetadata  `json:"metadata"`
	Status   ArgoCDAppStatus `json:"status"`
}

type ArgoCDMetadata struct {
	Name string `json:"name"`
}

type ArgoCDAppStatus struct {
	Health ArgoCDHealth `json:"health"`
	Sync   ArgoCDSync   `json:"sync"`
}

type ArgoCDHealth struct {
	Status string `json:"status"`
}

type ArgoCDSync struct {
	Status string `json:"status"`
}

type ArgoCDCollector struct {
	baseURL string
	token   string
	client  *http.Client
}

func NewArgoCDCollector(baseURL, token string) *ArgoCDCollector {
	return &ArgoCDCollector{
		baseURL: baseURL,
		token:   token,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *ArgoCDCollector) Collect(ctx context.Context) ([]Finding, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/applications", nil)
	if err != nil {
		return nil, err
	}
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("argocd list apps: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("argocd returned %d", resp.StatusCode)
	}

	var apps ArgoCDAppList
	if err := json.NewDecoder(resp.Body).Decode(&apps); err != nil {
		return nil, fmt.Errorf("decode argocd response: %w", err)
	}

	var findings []Finding
	now := time.Now()

	unhealthyStatuses := map[string]Severity{
		"Degraded":    SeverityCritical,
		"Missing":     SeverityCritical,
		"Unknown":     SeverityWarning,
		"Suspended":   SeverityInfo,
		"Progressing": SeverityInfo,
	}

	for _, app := range apps.Items {
		if sev, bad := unhealthyStatuses[app.Status.Health.Status]; bad && sev != SeverityInfo {
			findings = append(findings, Finding{
				Fingerprint: fmt.Sprintf("patrol:argocd:%s:health:%s", app.Metadata.Name, app.Status.Health.Status),
				Source:      "argocd",
				Severity:    sev,
				Title:       fmt.Sprintf("ArgoCD app %s", app.Status.Health.Status),
				Detail:      fmt.Sprintf("Application %s health is %s", app.Metadata.Name, app.Status.Health.Status),
				Data:        map[string]any{"app": app.Metadata.Name, "health": app.Status.Health.Status, "sync": app.Status.Sync.Status},
				Timestamp:   now,
			})
		}

		if app.Status.Sync.Status == "OutOfSync" {
			findings = append(findings, Finding{
				Fingerprint: fmt.Sprintf("patrol:argocd:%s:sync:OutOfSync", app.Metadata.Name),
				Source:      "argocd",
				Severity:    SeverityWarning,
				Title:       "ArgoCD app OutOfSync",
				Detail:      fmt.Sprintf("Application %s is out of sync", app.Metadata.Name),
				Data:        map[string]any{"app": app.Metadata.Name, "health": app.Status.Health.Status, "sync": app.Status.Sync.Status},
				Timestamp:   now,
			})
		}
	}

	return findings, nil
}

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type alertRulesResponse struct {
	Status string         `json:"status"`
	Data   alertRulesData `json:"data"`
}

type alertRulesData struct {
	Rules []alertRule `json:"rules"`
}

type alertRule struct {
	ID     string            `json:"id"`
	Name   string            `json:"alert"`
	State  string            `json:"state"`
	Labels map[string]string `json:"labels,omitempty"`
}

type AlertCollector struct {
	baseURL string
	token   string
	client  *http.Client
}

func NewAlertCollector(baseURL, token string) *AlertCollector {
	return &AlertCollector{
		baseURL: baseURL,
		token:   token,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *AlertCollector) Collect(ctx context.Context) ([]Finding, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/rules", nil)
	if err != nil {
		return nil, err
	}
	if c.token != "" {
		req.Header.Set("SIGNOZ-API-KEY", c.token)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("signoz list alerts: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("signoz returned %d", resp.StatusCode)
	}

	var result alertRulesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode signoz response: %w", err)
	}

	var findings []Finding
	now := time.Now()

	for _, rule := range result.Data.Rules {
		if rule.State != "firing" {
			continue
		}

		severity := mapSeverity(rule.Labels["severity"])

		findings = append(findings, Finding{
			Fingerprint: fmt.Sprintf("patrol.alert.%s", rule.ID),
			Source:      "signoz:alert",
			Severity:    severity,
			Title:       rule.Name,
			Detail:      fmt.Sprintf("Alert %q (rule %s) is firing", rule.Name, rule.ID),
			Data: map[string]any{
				"rule_id":  rule.ID,
				"labels":   rule.Labels,
				"severity": rule.Labels["severity"],
			},
			Timestamp: now,
		})
	}

	return findings, nil
}

func mapSeverity(s string) Severity {
	switch s {
	case "critical":
		return SeverityCritical
	case "warning":
		return SeverityWarning
	default:
		return SeverityInfo
	}
}

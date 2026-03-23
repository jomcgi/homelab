package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAlertCollector_FiringAlerts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/rules" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-42",
						Name:  "Pod OOMKilled",
						State: "firing",
						Labels: map[string]string{
							"namespace": "trips",
							"service":   "imgproxy",
							"severity":  "warning",
						},
					},
					{
						ID:    "rule-43",
						Name:  "Node NotReady",
						State: "inactive",
						Labels: map[string]string{
							"severity": "critical",
						},
					},
					{
						ID:    "rule-44",
						Name:  "High Error Rate",
						State: "firing",
						Labels: map[string]string{
							"service":  "api-gateway",
							"severity": "critical",
						},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 2 {
		t.Fatalf("expected 2 findings (only firing), got %d", len(findings))
	}

	if findings[0].Fingerprint != "patrol.alert.rule-42" {
		t.Errorf("expected fingerprint patrol.alert.rule-42, got %s", findings[0].Fingerprint)
	}
	if findings[0].Severity != SeverityWarning {
		t.Errorf("expected warning severity, got %s", findings[0].Severity)
	}
	if findings[1].Fingerprint != "patrol.alert.rule-44" {
		t.Errorf("expected fingerprint patrol.alert.rule-44, got %s", findings[1].Fingerprint)
	}
	if findings[1].Severity != SeverityCritical {
		t.Errorf("expected critical severity, got %s", findings[1].Severity)
	}
}

func TestAlertCollector_NoFiringAlerts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-1",
						Name:  "Healthy",
						State: "inactive",
						Labels: map[string]string{
							"severity": "warning",
						},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}

func TestAlertCollector_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	_, err := collector.Collect(context.Background())
	if err == nil {
		t.Fatal("expected error on 500 response")
	}
}

// TestMapSeverity verifies that mapSeverity maps well-known strings to their
// corresponding Severity constants and falls back to SeverityInfo for any
// unrecognised input — including the string "info" itself, which is not a
// special case in the switch.
func TestMapSeverity(t *testing.T) {
	cases := []struct {
		input string
		want  Severity
	}{
		{"critical", SeverityCritical},
		{"warning", SeverityWarning},
		// Default branch: "info" is not a named case — falls through to default.
		{"info", SeverityInfo},
		// Completely unknown label.
		{"unknown", SeverityInfo},
		// Empty string.
		{"", SeverityInfo},
		// Upper-case variant — not matched, falls to default.
		{"CRITICAL", SeverityInfo},
	}

	for _, tc := range cases {
		t.Run(tc.input, func(t *testing.T) {
			got := mapSeverity(tc.input)
			if got != tc.want {
				t.Errorf("mapSeverity(%q) = %q, want %q", tc.input, got, tc.want)
			}
		})
	}
}

// TestAlertCollector_InfoSeverityFiring verifies that a firing alert with an
// unrecognised severity label (e.g. "info") is collected and assigned
// SeverityInfo via the mapSeverity default branch.
func TestAlertCollector_InfoSeverityFiring(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-100",
						Name:  "Low Disk Space",
						State: "firing",
						Labels: map[string]string{
							"severity": "info",
						},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Severity != SeverityInfo {
		t.Errorf("expected SeverityInfo for 'info' label, got %s", findings[0].Severity)
	}
}

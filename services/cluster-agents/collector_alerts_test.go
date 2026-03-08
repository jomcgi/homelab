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
						ID:       42,
						Name:     "Pod OOMKilled",
						State:    "firing",
						Severity: "warning",
						Labels:   map[string]string{"namespace": "trips", "service": "imgproxy"},
					},
					{
						ID:       43,
						Name:     "Node NotReady",
						State:    "inactive",
						Severity: "critical",
					},
					{
						ID:       44,
						Name:     "High Error Rate",
						State:    "firing",
						Severity: "critical",
						Labels:   map[string]string{"service": "api-gateway"},
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

	if findings[0].Fingerprint != "patrol.alert.42" {
		t.Errorf("expected fingerprint patrol.alert.42, got %s", findings[0].Fingerprint)
	}
	if findings[0].Severity != SeverityWarning {
		t.Errorf("expected warning severity, got %s", findings[0].Severity)
	}
	if findings[1].Fingerprint != "patrol.alert.44" {
		t.Errorf("expected fingerprint patrol.alert.44, got %s", findings[1].Fingerprint)
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
					{ID: 1, Name: "Healthy", State: "inactive", Severity: "warning"},
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

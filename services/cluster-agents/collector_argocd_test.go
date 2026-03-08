package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestArgoCDCollector_FindsDegraded(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ArgoCDAppList{
			Items: []ArgoCDApp{
				{
					Metadata: ArgoCDMetadata{Name: "my-app"},
					Status: ArgoCDAppStatus{
						Health: ArgoCDHealth{Status: "Degraded"},
						Sync:   ArgoCDSync{Status: "Synced"},
					},
				},
				{
					Metadata: ArgoCDMetadata{Name: "healthy-app"},
					Status: ArgoCDAppStatus{
						Health: ArgoCDHealth{Status: "Healthy"},
						Sync:   ArgoCDSync{Status: "Synced"},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewArgoCDCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d: %+v", len(findings), findings)
	}
	if findings[0].Title != "ArgoCD app Degraded" {
		t.Errorf("unexpected title: %s", findings[0].Title)
	}
}

func TestArgoCDCollector_FindsOutOfSync(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ArgoCDAppList{
			Items: []ArgoCDApp{{
				Metadata: ArgoCDMetadata{Name: "drifted-app"},
				Status: ArgoCDAppStatus{
					Health: ArgoCDHealth{Status: "Healthy"},
					Sync:   ArgoCDSync{Status: "OutOfSync"},
				},
			}},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewArgoCDCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Severity != SeverityWarning {
		t.Errorf("expected warning severity, got %s", findings[0].Severity)
	}
}

package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrichPipeline(t *testing.T) {
	// Mock LLM server returning structured JSON.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := map[string]any{
			"choices": []map[string]any{
				{"message": map[string]any{
					"content": `[{"title":"Debug CI","summary":"Investigate BuildBuddy failures"},{"title":"Fix Code","summary":"Apply fixes from CI analysis"}]`,
				}},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	steps := []PipelineStep{
		{Agent: "ci-debug", Task: "Debug the CI failure", Condition: "always"},
		{Agent: "code-fix", Task: "Fix the issue", Condition: "on success"},
	}

	enrichments, err := enrichPipeline(context.Background(), server.URL, steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(enrichments) != 2 {
		t.Fatalf("expected 2 enrichments, got %d", len(enrichments))
	}
	if enrichments[0].Title != "Debug CI" {
		t.Fatalf("expected 'Debug CI', got %q", enrichments[0].Title)
	}
}

func TestEnrichPipeline_InferenceUnavailable(t *testing.T) {
	// When inference URL is empty, return nil (graceful degradation).
	enrichments, err := enrichPipeline(context.Background(), "", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if enrichments != nil {
		t.Fatalf("expected nil enrichments, got %v", enrichments)
	}
}

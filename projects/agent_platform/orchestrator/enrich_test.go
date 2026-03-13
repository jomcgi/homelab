package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrichPipeline(t *testing.T) {
	// Mock LLM server returning old array format (backward-compat).
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

	result, err := enrichPipeline(context.Background(), server.URL, steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Steps) != 2 {
		t.Fatalf("expected 2 enrichments, got %d", len(result.Steps))
	}
	if result.Steps[0].Title != "Debug CI" {
		t.Fatalf("expected 'Debug CI', got %q", result.Steps[0].Title)
	}
}

func TestEnrichPipeline_NewFormat(t *testing.T) {
	// Mock LLM server returning new object format with pipeline_summary.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := map[string]any{
			"choices": []map[string]any{
				{"message": map[string]any{
					"content": `{"steps":[{"title":"Debug CI","summary":"Investigate failures"},{"title":"Fix Code","summary":"Apply fixes"}],"pipeline_summary":"Debug and fix CI failures"}`,
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

	result, err := enrichPipeline(context.Background(), server.URL, steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Steps) != 2 {
		t.Fatalf("expected 2 enrichments, got %d", len(result.Steps))
	}
	if result.Steps[0].Title != "Debug CI" {
		t.Fatalf("expected 'Debug CI', got %q", result.Steps[0].Title)
	}
	if result.PipelineSummary != "Debug and fix CI failures" {
		t.Fatalf("expected pipeline summary, got %q", result.PipelineSummary)
	}
}

func TestEnrichPipeline_InferenceUnavailable(t *testing.T) {
	// When inference URL is empty, return zero value (graceful degradation).
	result, err := enrichPipeline(context.Background(), "", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Steps) != 0 {
		t.Fatalf("expected empty steps, got %v", result.Steps)
	}
}

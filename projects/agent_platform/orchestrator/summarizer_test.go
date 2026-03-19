package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// chatResponse builds a minimal OpenAI-compatible chat completion response.
func chatResponse(content string) string {
	resp := struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}{
		Choices: []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		}{
			{Message: struct {
				Content string `json:"content"`
			}{Content: content}},
		},
	}
	b, _ := json.Marshal(resp)
	return string(b)
}

func TestSummarizer_SummarizeTask(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(chatResponse(`{"title":"Deploy Auth Service"}`)))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "deploy the auth service to production")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "Deploy Auth Service" {
		t.Errorf("got title %q, want %q", title, "Deploy Auth Service")
	}
}

func TestSummarizer_SummarizePlan(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(chatResponse(`{"title":"Auth Deployment","summary":"Deploys auth service with config updates."}`)))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	plan := []PlanStep{
		{Agent: "k8s", Description: "Apply deployment manifest", Status: "completed"},
		{Agent: "config", Description: "Update config map", Status: "pending"},
	}
	title, summary, err := s.SummarizePlan(context.Background(), "deploy auth", plan)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "Auth Deployment" {
		t.Errorf("got title %q, want %q", title, "Auth Deployment")
	}
	if summary != "Deploys auth service with config updates." {
		t.Errorf("got summary %q, want %q", summary, "Deploys auth service with config updates.")
	}
}

func TestSummarizer_NilSafe(t *testing.T) {
	var s *Summarizer

	title, err := s.SummarizeTask(context.Background(), "some task")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "" {
		t.Errorf("expected empty title, got %q", title)
	}

	title2, summary, err := s.SummarizePlan(context.Background(), "some task", []PlanStep{{Agent: "a", Description: "d", Status: "pending"}})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title2 != "" || summary != "" {
		t.Errorf("expected empty strings, got title=%q summary=%q", title2, summary)
	}
}

func TestSummarizer_EmptyInferenceURL(t *testing.T) {
	s := NewSummarizer("", "test-model", slog.Default())

	title, err := s.SummarizeTask(context.Background(), "some task")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title != "" {
		t.Errorf("expected empty title, got %q", title)
	}

	title2, summary, err := s.SummarizePlan(context.Background(), "some task", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if title2 != "" || summary != "" {
		t.Errorf("expected empty strings, got title=%q summary=%q", title2, summary)
	}
}

func TestSummarizer_LLMError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "some task")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if title != "" {
		t.Errorf("expected empty title on error, got %q", title)
	}
}

// TestSummarizer_InvalidJSONBody verifies that callLLM returns an error when
// the server responds with HTTP 200 but a body that is not valid JSON.
func TestSummarizer_InvalidJSONBody(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("this is not valid json {{ garbage"))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "some task")
	if err == nil {
		t.Fatal("expected error for invalid JSON response body, got nil")
	}
	if title != "" {
		t.Errorf("expected empty title on parse error, got %q", title)
	}
}

// TestSummarizer_EmptyChoices verifies that callLLM returns an error when the
// server responds with HTTP 200 and valid JSON but an empty choices array.
func TestSummarizer_EmptyChoices(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"choices":[]}`))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(context.Background(), "some task")
	if err == nil {
		t.Fatal("expected error for empty choices array, got nil")
	}
	if title != "" {
		t.Errorf("expected empty title when choices is empty, got %q", title)
	}
	if !strings.Contains(err.Error(), "no choices") {
		t.Errorf("expected 'no choices' in error message, got %q", err.Error())
	}
}

// TestSummarizer_ContextCancellation verifies that callLLM propagates context
// cancellation errors so callers can detect timeouts and cancellations.
func TestSummarizer_ContextCancellation(t *testing.T) {
	// Use a server that blocks until its own request context is done, ensuring
	// we actually exercise the HTTP client cancellation path.
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-r.Context().Done():
		case <-done:
		}
	}))
	defer close(done)
	defer srv.Close()

	// Cancel the context before making the request.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	title, err := s.SummarizeTask(ctx, "some task")
	if err == nil {
		t.Fatal("expected error for pre-cancelled context, got nil")
	}
	if title != "" {
		t.Errorf("expected empty title on context cancellation, got %q", title)
	}
}

package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
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

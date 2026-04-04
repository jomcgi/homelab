package main

// summarizer_coverage_test.go extends summarizer_test.go with table-driven
// tests for SummarizePlan error paths and callLLM request-format validation.
// The existing summarizer_test.go fully covers SummarizeTask error paths;
// this file mirrors that coverage for SummarizePlan.

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---- SummarizePlan error paths (table-driven) --------------------------------

// TestSummarizePlan_ErrorPaths verifies that SummarizePlan propagates errors
// from callLLM to the caller in the same way that SummarizeTask does.
// Each sub-test exercises a different server-side failure mode.
func TestSummarizePlan_ErrorPaths(t *testing.T) {
	samplePlan := []PlanStep{
		{Agent: "researcher", Description: "Investigate the problem", Status: "completed"},
		{Agent: "coder", Description: "Write the fix", Status: "running"},
	}

	tests := []struct {
		name        string
		handler     http.HandlerFunc
		wantErr     bool
		errContains string
	}{
		{
			name: "LLM returns HTTP 500",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusInternalServerError)
			},
			wantErr:     true,
			errContains: "inference returned 500",
		},
		{
			name: "LLM returns invalid JSON body",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				w.Write([]byte("this is not valid json {{ garbage"))
			},
			wantErr:     true,
			errContains: "",
		},
		{
			name: "LLM returns valid JSON but empty choices array",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.Write([]byte(`{"choices":[]}`))
			},
			wantErr:     true,
			errContains: "no choices",
		},
		{
			name: "LLM returns choices with non-JSON content",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.Write([]byte(chatResponse("not json at all")))
			},
			wantErr:     true,
			errContains: "",
		},
		{
			name: "LLM returns HTTP 429 Too Many Requests",
			handler: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusTooManyRequests)
			},
			wantErr:     true,
			errContains: "inference returned 429",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(tc.handler)
			defer srv.Close()

			s := NewSummarizer(srv.URL, "test-model", slog.Default())
			title, summary, err := s.SummarizePlan(context.Background(), "some task", samplePlan)

			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil (title=%q, summary=%q)", title, summary)
				}
				if tc.errContains != "" && !strings.Contains(err.Error(), tc.errContains) {
					t.Errorf("error = %q, want substring %q", err.Error(), tc.errContains)
				}
			} else {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
			}

			// On error both return values must be empty strings.
			if tc.wantErr {
				if title != "" {
					t.Errorf("title = %q, want empty on error", title)
				}
				if summary != "" {
					t.Errorf("summary = %q, want empty on error", summary)
				}
			}
		})
	}
}

// TestSummarizePlan_ContextCancellation verifies that SummarizePlan propagates
// context cancellation errors (mirrors TestSummarizer_ContextCancellation for
// SummarizeTask).
func TestSummarizePlan_ContextCancellation(t *testing.T) {
	done := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-r.Context().Done():
		case <-done:
		}
	}))
	defer close(done)
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before the call

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	plan := []PlanStep{{Agent: "a", Description: "step", Status: "pending"}}
	title, summary, err := s.SummarizePlan(ctx, "some task", plan)

	if err == nil {
		t.Fatal("expected error for pre-cancelled context, got nil")
	}
	if title != "" {
		t.Errorf("title = %q, want empty on context cancellation", title)
	}
	if summary != "" {
		t.Errorf("summary = %q, want empty on context cancellation", summary)
	}
}

// ---- SummarizePlan edge cases (table-driven) ---------------------------------

// TestSummarizePlan_EdgeCases covers boundary behaviours of SummarizePlan that
// are independent of the HTTP server response code.
func TestSummarizePlan_EdgeCases(t *testing.T) {
	tests := []struct {
		name        string
		task        string
		plan        []PlanStep
		wantTitle   string
		wantSummary string
	}{
		{
			name:        "nil plan",
			task:        "task with nil plan",
			plan:        nil,
			wantTitle:   "Task Title",
			wantSummary: "Short summary.",
		},
		{
			name:        "empty plan (zero steps)",
			task:        "task with no plan steps",
			plan:        []PlanStep{},
			wantTitle:   "Task Title",
			wantSummary: "Short summary.",
		},
		{
			name: "single step plan",
			task: "run tests",
			plan: []PlanStep{
				{Agent: "tester", Description: "Run all tests", Status: "completed"},
			},
			wantTitle:   "Task Title",
			wantSummary: "Short summary.",
		},
		{
			name: "plan with all status values",
			task: "multi-phase task",
			plan: []PlanStep{
				{Agent: "a", Description: "Step A", Status: "completed"},
				{Agent: "b", Description: "Step B", Status: "running"},
				{Agent: "c", Description: "Step C", Status: "pending"},
				{Agent: "d", Description: "Step D", Status: "failed"},
			},
			wantTitle:   "Task Title",
			wantSummary: "Short summary.",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.Write([]byte(chatResponse(`{"title":"Task Title","summary":"Short summary."}`)))
			}))
			defer srv.Close()

			s := NewSummarizer(srv.URL, "test-model", slog.Default())
			title, summary, err := s.SummarizePlan(context.Background(), tc.task, tc.plan)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if title != tc.wantTitle {
				t.Errorf("title = %q, want %q", title, tc.wantTitle)
			}
			if summary != tc.wantSummary {
				t.Errorf("summary = %q, want %q", summary, tc.wantSummary)
			}
		})
	}
}

// ---- callLLM request-format validation ---------------------------------------

// TestCallLLM_RequestFormat verifies that callLLM sends the expected JSON
// structure to the inference endpoint. This exercises the request-building
// logic regardless of the response: model name, message roles, temperature,
// max_tokens, and the structured response_format with json_schema.
func TestCallLLM_RequestFormat(t *testing.T) {
	const model = "gpt-4o-mini"
	const systemPrompt = "You are a helpful assistant."
	const userPrompt = "Summarise this task."

	var capturedBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %q, want POST", r.Method)
		}
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("path = %q, want /v1/chat/completions", r.URL.Path)
		}
		if ct := r.Header.Get("Content-Type"); ct != "application/json" {
			t.Errorf("Content-Type = %q, want application/json", ct)
		}
		capturedBody, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(chatResponse(`{"title":"Test Title"}`)))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, model, slog.Default())
	_, _ = s.SummarizeTask(context.Background(), "some task")

	// Parse the captured request body and validate key fields.
	var req map[string]interface{}
	if err := json.Unmarshal(capturedBody, &req); err != nil {
		t.Fatalf("request body is not valid JSON: %v\nbody: %s", err, capturedBody)
	}

	// Model name must match what was configured.
	if req["model"] != model {
		t.Errorf("model = %v, want %q", req["model"], model)
	}

	// Messages array must have system + user entries.
	msgs, ok := req["messages"].([]interface{})
	if !ok || len(msgs) != 2 {
		t.Fatalf("messages = %v, want 2-element array", req["messages"])
	}
	sysMsg, _ := msgs[0].(map[string]interface{})
	if sysMsg["role"] != "system" {
		t.Errorf("messages[0].role = %v, want system", sysMsg["role"])
	}
	userMsg, _ := msgs[1].(map[string]interface{})
	if userMsg["role"] != "user" {
		t.Errorf("messages[1].role = %v, want user", userMsg["role"])
	}

	// Temperature must be present (0.3 as a number).
	temp, ok := req["temperature"].(float64)
	if !ok {
		t.Errorf("temperature missing or wrong type: %v", req["temperature"])
	} else if temp != 0.3 {
		t.Errorf("temperature = %v, want 0.3", temp)
	}

	// max_tokens must be present (256).
	maxTok, ok := req["max_tokens"].(float64)
	if !ok {
		t.Errorf("max_tokens missing or wrong type: %v", req["max_tokens"])
	} else if maxTok != 256 {
		t.Errorf("max_tokens = %v, want 256", maxTok)
	}

	// response_format must use json_schema type.
	rf, ok := req["response_format"].(map[string]interface{})
	if !ok {
		t.Fatalf("response_format missing or wrong type: %v", req["response_format"])
	}
	if rf["type"] != "json_schema" {
		t.Errorf("response_format.type = %v, want json_schema", rf["type"])
	}
}

// TestCallLLM_SummarizePlanRequestIncludesPlanSteps verifies that the user
// message sent to the LLM by SummarizePlan includes the formatted plan steps.
// This confirms that the plan summary prompt is constructed correctly.
func TestCallLLM_SummarizePlanRequestIncludesPlanSteps(t *testing.T) {
	plan := []PlanStep{
		{Agent: "researcher", Description: "Investigate root cause", Status: "completed"},
		{Agent: "coder", Description: "Write patch", Status: "running"},
	}

	var capturedBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedBody, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(chatResponse(`{"title":"Bug Fix","summary":"Fixed the bug."}`)))
	}))
	defer srv.Close()

	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	_, _, err := s.SummarizePlan(context.Background(), "fix the login bug", plan)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var req map[string]interface{}
	if err := json.Unmarshal(capturedBody, &req); err != nil {
		t.Fatalf("request body invalid JSON: %v", err)
	}

	msgs, _ := req["messages"].([]interface{})
	if len(msgs) < 2 {
		t.Fatalf("expected at least 2 messages, got %d", len(msgs))
	}
	userMsg, _ := msgs[1].(map[string]interface{})
	content, _ := userMsg["content"].(string)

	// The user message must contain the task and each plan step.
	for _, want := range []string{
		"fix the login bug",
		"Investigate root cause",
		"Write patch",
		"researcher",
		"coder",
		"completed",
		"running",
	} {
		if !strings.Contains(content, want) {
			t.Errorf("user message does not contain %q\ncontent: %s", want, content)
		}
	}
}

// TestSummarizeTask_ReturnsTitle verifies that SummarizeTask returns exactly
// the "title" field from the JSON response — a table-driven companion to the
// existing non-table tests that also validates the field name extraction.
func TestSummarizeTask_ReturnsTitle(t *testing.T) {
	tests := []struct {
		name      string
		response  string // JSON content of the LLM message
		wantTitle string
		wantErr   bool
	}{
		{
			name:      "single word title",
			response:  `{"title":"Deploy"}`,
			wantTitle: "Deploy",
		},
		{
			name:      "multi-word title",
			response:  `{"title":"Fix flaky integration tests"}`,
			wantTitle: "Fix flaky integration tests",
		},
		{
			name:      "title with punctuation",
			response:  `{"title":"Update docs: add API reference"}`,
			wantTitle: "Update docs: add API reference",
		},
		{
			name:     "missing title field returns empty string",
			response: `{"summary":"no title here"}`,
			// title field absent → result["title"] == "" (zero value for string map)
			wantTitle: "",
			wantErr:   false,
		},
		{
			name:     "malformed JSON in content",
			response: `{invalid json`,
			wantErr:  true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.Write([]byte(chatResponse(tc.response)))
			}))
			defer srv.Close()

			s := NewSummarizer(srv.URL, "test-model", slog.Default())
			title, err := s.SummarizeTask(context.Background(), "some task")

			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil (title=%q)", title)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if title != tc.wantTitle {
				t.Errorf("title = %q, want %q", title, tc.wantTitle)
			}
		})
	}
}

// TestSummarizePlan_ReturnsTitleAndSummary is the table-driven companion to
// TestSummarizer_SummarizePlan, verifying both return values across multiple
// server response variations.
func TestSummarizePlan_ReturnsTitleAndSummary(t *testing.T) {
	plan := []PlanStep{
		{Agent: "agent", Description: "Do work", Status: "completed"},
	}

	tests := []struct {
		name        string
		response    string
		wantTitle   string
		wantSummary string
		wantErr     bool
	}{
		{
			name:        "title and summary both present",
			response:    `{"title":"Deploy Service","summary":"Deploys the auth service."}`,
			wantTitle:   "Deploy Service",
			wantSummary: "Deploys the auth service.",
		},
		{
			name:        "title only present",
			response:    `{"title":"Fix Bug"}`,
			wantTitle:   "Fix Bug",
			wantSummary: "",
		},
		{
			name:        "summary only present",
			response:    `{"summary":"Some summary"}`,
			wantTitle:   "",
			wantSummary: "Some summary",
		},
		{
			name:        "empty title and summary",
			response:    `{"title":"","summary":""}`,
			wantTitle:   "",
			wantSummary: "",
		},
		{
			name:     "invalid JSON content",
			response: `not json`,
			wantErr:  true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.Write([]byte(chatResponse(tc.response)))
			}))
			defer srv.Close()

			s := NewSummarizer(srv.URL, "test-model", slog.Default())
			title, summary, err := s.SummarizePlan(context.Background(), "task text", plan)

			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil (title=%q, summary=%q)", title, summary)
				}
				if title != "" || summary != "" {
					t.Errorf("expected empty returns on error, got title=%q summary=%q", title, summary)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if title != tc.wantTitle {
				t.Errorf("title = %q, want %q", title, tc.wantTitle)
			}
			if summary != tc.wantSummary {
				t.Errorf("summary = %q, want %q", summary, tc.wantSummary)
			}
		})
	}
}

package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// TestJobStatusValues verifies all status constants have the expected string values.
func TestJobStatusValues(t *testing.T) {
	cases := []struct {
		status JobStatus
		want   string
	}{
		{JobPending, "PENDING"},
		{JobRunning, "RUNNING"},
		{JobSucceeded, "SUCCEEDED"},
		{JobFailed, "FAILED"},
		{JobCancelled, "CANCELLED"},
	}
	for _, tc := range cases {
		if string(tc.status) != tc.want {
			t.Errorf("JobStatus %q: got %q, want %q", tc.want, tc.status, tc.want)
		}
	}
}

// TestSubmitRequest_OptionalFields verifies that optional fields in SubmitRequest
// are correctly omitted when zero-valued.
func TestSubmitRequest_OptionalFields(t *testing.T) {
	req := SubmitRequest{Task: "run the tests"}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	for _, key := range []string{"max_retries", "source", "tags"} {
		if strings.Contains(string(data), `"`+key+`"`) {
			t.Errorf("expected %q to be omitted when zero, got %s", key, data)
		}
	}
}

// TestSubmitRequest_WithAllFields verifies all SubmitRequest fields round-trip.
func TestSubmitRequest_WithAllFields(t *testing.T) {
	maxRetries := 3
	req := SubmitRequest{
		Task:       "build the image",
		MaxRetries: &maxRetries,
		Source:     "discord",
		Tags:       []string{"ci", "urgent"},
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got SubmitRequest
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if got.Task != req.Task {
		t.Errorf("Task: got %q, want %q", got.Task, req.Task)
	}
	if got.MaxRetries == nil || *got.MaxRetries != 3 {
		t.Errorf("MaxRetries: got %v, want 3", got.MaxRetries)
	}
	if got.Source != req.Source {
		t.Errorf("Source: got %q, want %q", got.Source, req.Source)
	}
	if len(got.Tags) != 2 || got.Tags[0] != "ci" || got.Tags[1] != "urgent" {
		t.Errorf("Tags: got %v, want [ci urgent]", got.Tags)
	}
}

// TestJobRecord_RoundTrip verifies JobRecord JSON serialisation round-trips correctly,
// including plan fields and LLM-generated title/summary fields.
func TestJobRecord_RoundTrip(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	job := JobRecord{
		ID:        "01J8Z4VPKF0000000000000000",
		Task:      "investigate traces",
		Profile:   "ci-debug",
		Status:    JobPending,
		CreatedAt: now,
		UpdatedAt: now,
		Source:    "discord",
		Tags:      []string{"ci", "urgent"},
		Title:     "Investigate Distributed Traces",
		Summary:   "Investigates distributed tracing issues in the monitoring stack.",
		Plan: []PlanStep{
			{Agent: "research", Description: "investigate", Status: "pending"},
			{Agent: "code-fix", Description: "fix it", Status: "pending"},
		},
		Attempts: []Attempt{},
	}

	data, err := json.Marshal(job)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got JobRecord
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if got.ID != job.ID {
		t.Errorf("ID: got %q, want %q", got.ID, job.ID)
	}
	if got.Status != JobPending {
		t.Errorf("Status: got %q, want PENDING", got.Status)
	}
	if got.Source != "discord" {
		t.Errorf("Source: got %q, want 'discord'", got.Source)
	}
	if len(got.Plan) != 2 {
		t.Fatalf("Plan: got %d steps, want 2", len(got.Plan))
	}
	if got.Plan[0].Agent != "research" {
		t.Errorf("Plan[0].Agent: got %q, want 'research'", got.Plan[0].Agent)
	}
	if got.Title != job.Title {
		t.Errorf("Title: got %q, want %q", got.Title, job.Title)
	}
	if got.Summary != job.Summary {
		t.Errorf("Summary: got %q, want %q", got.Summary, job.Summary)
	}
}

// TestJobRecord_OptionalFieldsOmitted verifies omitempty fields are absent when zero.
func TestJobRecord_OptionalFieldsOmitted(t *testing.T) {
	job := JobRecord{
		ID:        "01J8Z4VPKF0000000000000000",
		Task:      "test",
		Status:    JobRunning,
		CreatedAt: time.Now().UTC(),
		UpdatedAt: time.Now().UTC(),
		Attempts:  []Attempt{},
	}

	data, err := json.Marshal(job)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	for _, key := range []string{"profile", "github_issue", "debug_mode", "failure_summary", "plan", "tags", "title", "summary"} {
		if strings.Contains(string(data), `"`+key+`"`) {
			t.Errorf("expected %q to be omitted when zero, got %s", key, data)
		}
	}
}

// TestGooseResult_RoundTrip verifies GooseResult JSON round-trip.
func TestGooseResult_RoundTrip(t *testing.T) {
	result := GooseResult{
		Type:    "pr",
		URL:     "https://github.com/example/pull/1",
		Summary: "fix it",
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got GooseResult
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if got.Type != result.Type {
		t.Errorf("Type: got %q, want %q", got.Type, result.Type)
	}
	if got.URL != result.URL {
		t.Errorf("URL: got %q, want %q", got.URL, result.URL)
	}
	if got.Summary != result.Summary {
		t.Errorf("Summary: got %q, want %q", got.Summary, result.Summary)
	}
}

// TestPlanStep_RoundTrip verifies PlanStep JSON round-trip with various statuses.
func TestPlanStep_RoundTrip(t *testing.T) {
	cases := []struct {
		name   string
		step   PlanStep
		status string
	}{
		{"pending", PlanStep{Agent: "research", Description: "investigate", Status: "pending"}, "pending"},
		{"running", PlanStep{Agent: "code-fix", Description: "fix", Status: "running"}, "running"},
		{"completed", PlanStep{Agent: "notifier", Description: "notify", Status: "completed"}, "completed"},
		{"failed", PlanStep{Agent: "ci-debug", Description: "debug", Status: "failed"}, "failed"},
		{"skipped", PlanStep{Agent: "cleanup", Description: "clean up", Status: "skipped"}, "skipped"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			data, err := json.Marshal(tc.step)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			var got PlanStep
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			if got.Status != tc.status {
				t.Errorf("Status: got %q, want %q", got.Status, tc.status)
			}
			if got.Agent != tc.step.Agent {
				t.Errorf("Agent: got %q, want %q", got.Agent, tc.step.Agent)
			}
			if got.Description != tc.step.Description {
				t.Errorf("Description: got %q, want %q", got.Description, tc.step.Description)
			}
		})
	}
}

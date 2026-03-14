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
		{JobBlocked, "BLOCKED"},
		{JobSkipped, "SKIPPED"},
	}
	for _, tc := range cases {
		if string(tc.status) != tc.want {
			t.Errorf("JobStatus %q: got %q, want %q", tc.want, tc.status, tc.want)
		}
	}
}

// TestAgentInfo_RecipePath verifies AgentInfo serialises the new RecipePath field
// (added in the recipe-path refactor) under the JSON key "recipePath".
func TestAgentInfo_RecipePath(t *testing.T) {
	agent := AgentInfo{
		ID:          "ci-debug",
		Label:       "CI Debug",
		Icon:        "gear",
		Background:  "#dbeafe",
		Foreground:  "#1e40af",
		Description: "Debug failing CI jobs",
		Category:    "analyse",
		RecipePath:  "projects/agent_platform/goose_agent/image/recipes/ci-debug.yaml",
	}

	data, err := json.Marshal(agent)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	// Verify the JSON key is "recipePath" (camelCase as declared in the struct tag).
	if !strings.Contains(string(data), `"recipePath"`) {
		t.Errorf("expected JSON key 'recipePath' in %s", data)
	}
	// Old fields must NOT appear.
	if strings.Contains(string(data), `"recipe"`) {
		t.Errorf("unexpected 'recipe' field in %s", data)
	}
	if strings.Contains(string(data), `"model"`) {
		t.Errorf("unexpected 'model' field in %s", data)
	}

	var got AgentInfo
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.RecipePath != agent.RecipePath {
		t.Errorf("RecipePath round-trip: got %q, want %q", got.RecipePath, agent.RecipePath)
	}
}

// TestAgentInfo_RecipePathOmitempty verifies that an empty RecipePath is omitted
// from the JSON output (the field has omitempty).
func TestAgentInfo_RecipePathOmitempty(t *testing.T) {
	agent := AgentInfo{
		ID:    "no-recipe",
		Label: "No Recipe Agent",
	}

	data, err := json.Marshal(agent)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	if strings.Contains(string(data), "recipePath") {
		t.Errorf("expected recipePath to be omitted when empty, got %s", data)
	}
}

// TestAgentsResponse_RoundTrip verifies the AgentsResponse wrapper marshals and
// unmarshals cleanly.
func TestAgentsResponse_RoundTrip(t *testing.T) {
	resp := AgentsResponse{
		Agents: []AgentInfo{
			{ID: "a", Label: "Agent A", RecipePath: "recipes/a.yaml"},
			{ID: "b", Label: "Agent B"},
		},
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got AgentsResponse
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(got.Agents) != 2 {
		t.Fatalf("expected 2 agents, got %d", len(got.Agents))
	}
	if got.Agents[0].RecipePath != "recipes/a.yaml" {
		t.Errorf("agents[0].RecipePath = %q, want %q", got.Agents[0].RecipePath, "recipes/a.yaml")
	}
	if got.Agents[1].RecipePath != "" {
		t.Errorf("agents[1].RecipePath should be empty, got %q", got.Agents[1].RecipePath)
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

	// profile, max_retries, source, tags should all be absent.
	for _, key := range []string{"profile", "max_retries", "source", "tags"} {
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
		Profile:    "ci-debug",
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
	if got.Profile != req.Profile {
		t.Errorf("Profile: got %q, want %q", got.Profile, req.Profile)
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

// TestJobRecord_PipelineFields verifies that pipeline execution fields
// (PipelineID, StepIndex, StepCondition) round-trip correctly through JSON.
func TestJobRecord_PipelineFields(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	job := JobRecord{
		ID:              "01J8Z4VPKF0000000000000000",
		Task:            "investigate traces",
		Status:          JobBlocked,
		CreatedAt:       now,
		UpdatedAt:       now,
		PipelineID:      "01J8Z4VPKF0000000000000001",
		StepIndex:       1,
		StepCondition:   "on success",
		Title:           "Investigate SigNoz traces",
		PipelineSummary: "3-step debug pipeline",
		Attempts:        []Attempt{},
	}

	data, err := json.Marshal(job)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got JobRecord
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if got.PipelineID != job.PipelineID {
		t.Errorf("PipelineID: got %q, want %q", got.PipelineID, job.PipelineID)
	}
	if got.StepIndex != 1 {
		t.Errorf("StepIndex: got %d, want 1", got.StepIndex)
	}
	if got.StepCondition != "on success" {
		t.Errorf("StepCondition: got %q, want 'on success'", got.StepCondition)
	}
	if got.Status != JobBlocked {
		t.Errorf("Status: got %q, want BLOCKED", got.Status)
	}
	if got.Title != job.Title {
		t.Errorf("Title: got %q, want %q", got.Title, job.Title)
	}
	if got.PipelineSummary != job.PipelineSummary {
		t.Errorf("PipelineSummary: got %q, want %q", got.PipelineSummary, job.PipelineSummary)
	}
}

// TestPipelineStep_RoundTrip verifies PipelineStep JSON round-trip.
func TestPipelineStep_RoundTrip(t *testing.T) {
	cases := []struct {
		name      string
		step      PipelineStep
		wantCond  string
	}{
		{"always", PipelineStep{Agent: "ci-debug", Task: "debug", Condition: "always"}, "always"},
		{"on success", PipelineStep{Agent: "code-fix", Task: "fix", Condition: "on success"}, "on success"},
		{"on failure", PipelineStep{Agent: "notifier", Task: "notify", Condition: "on failure"}, "on failure"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			data, err := json.Marshal(tc.step)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			var got PipelineStep
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("unmarshal: %v", err)
			}
			if got.Condition != tc.wantCond {
				t.Errorf("Condition: got %q, want %q", got.Condition, tc.wantCond)
			}
			if got.Agent != tc.step.Agent {
				t.Errorf("Agent: got %q, want %q", got.Agent, tc.step.Agent)
			}
			if got.Task != tc.step.Task {
				t.Errorf("Task: got %q, want %q", got.Task, tc.step.Task)
			}
		})
	}
}

// TestGooseResult_PipelineField verifies GooseResult can hold pipeline steps.
func TestGooseResult_PipelineField(t *testing.T) {
	result := GooseResult{
		Type:    "pipeline",
		URL:     "https://gist.github.com/example/abc",
		Summary: "3-step debug pipeline",
		Pipeline: []PipelineStep{
			{Agent: "research", Task: "investigate", Condition: "always"},
			{Agent: "code-fix", Task: "fix it", Condition: "on success"},
			{Agent: "notifier", Task: "notify", Condition: "always"},
		},
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got GooseResult
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if len(got.Pipeline) != 3 {
		t.Fatalf("Pipeline: got %d steps, want 3", len(got.Pipeline))
	}
	if got.Pipeline[1].Condition != "on success" {
		t.Errorf("Pipeline[1].Condition: got %q, want 'on success'", got.Pipeline[1].Condition)
	}
}

// TestGooseResult_PipelineOmitempty verifies Pipeline is omitted when empty.
func TestGooseResult_PipelineOmitempty(t *testing.T) {
	result := GooseResult{Type: "pr", URL: "https://github.com/example/pull/1", Summary: "fix it"}
	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(data), "pipeline") {
		t.Errorf("expected pipeline to be omitted when empty, got %s", data)
	}
}

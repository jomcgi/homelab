package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func newTestRunner() *runner {
	return &runner{state: StateIdle}
}

func TestHandleHealth(t *testing.T) {
	r := newTestRunner()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	r.handleHealth(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("expected application/json, got %s", ct)
	}
	if body := rec.Body.String(); body != `{"status":"ok"}` {
		t.Fatalf("unexpected body: %s", body)
	}
}

func TestHandleStatus_Idle(t *testing.T) {
	r := newTestRunner()
	req := httptest.NewRequest(http.MethodGet, "/status", nil)
	rec := httptest.NewRecorder()

	r.handleStatus(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp StatusResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.State != StateIdle {
		t.Fatalf("expected state=idle, got %s", resp.State)
	}
	if resp.PID != 0 {
		t.Fatalf("expected pid=0, got %d", resp.PID)
	}
	if resp.ExitCode != nil {
		t.Fatalf("expected no exit_code, got %d", *resp.ExitCode)
	}
}

func TestHandleStatus_Done(t *testing.T) {
	r := newTestRunner()
	now := time.Now().Truncate(time.Second)
	code := 0
	r.state = StateDone
	r.exitCode = &code
	r.startedAt = &now

	req := httptest.NewRequest(http.MethodGet, "/status", nil)
	rec := httptest.NewRecorder()

	r.handleStatus(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp StatusResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.State != StateDone {
		t.Fatalf("expected state=done, got %s", resp.State)
	}
	if resp.ExitCode == nil || *resp.ExitCode != 0 {
		t.Fatalf("expected exit_code=0, got %v", resp.ExitCode)
	}
	if resp.StartedAt == nil {
		t.Fatal("expected started_at to be set")
	}
	if !resp.StartedAt.Truncate(time.Second).Equal(now) {
		t.Fatalf("expected started_at=%v, got %v", now, *resp.StartedAt)
	}
}

func TestHandleOutput_Empty(t *testing.T) {
	r := newTestRunner()
	req := httptest.NewRequest(http.MethodGet, "/output", nil)
	rec := httptest.NewRecorder()

	r.handleOutput(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if body := rec.Body.String(); body != "" {
		t.Fatalf("expected empty body, got %q", body)
	}
	if off := rec.Header().Get("X-Output-Offset"); off != "0" {
		t.Fatalf("expected X-Output-Offset=0, got %s", off)
	}
}

func TestHandleOutput_WithOffset(t *testing.T) {
	r := newTestRunner()
	r.output = []byte("hello world")

	req := httptest.NewRequest(http.MethodGet, "/output?offset=6", nil)
	rec := httptest.NewRecorder()

	r.handleOutput(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if body := rec.Body.String(); body != "world" {
		t.Fatalf("expected body=%q, got %q", "world", body)
	}
	if off := rec.Header().Get("X-Output-Offset"); off != "11" {
		t.Fatalf("expected X-Output-Offset=11, got %s", off)
	}
}

func TestHandleOutput_OffsetBeyondEnd(t *testing.T) {
	r := newTestRunner()
	r.output = []byte("short")

	req := httptest.NewRequest(http.MethodGet, "/output?offset=100", nil)
	rec := httptest.NewRecorder()

	r.handleOutput(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if body := rec.Body.String(); body != "" {
		t.Fatalf("expected empty body, got %q", body)
	}
}

func TestHandleOutput_InvalidOffset(t *testing.T) {
	r := newTestRunner()

	tests := []struct {
		name   string
		offset string
	}{
		{"negative", "-1"},
		{"non-numeric", "abc"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/output?offset="+tc.offset, nil)
			rec := httptest.NewRecorder()

			r.handleOutput(rec, req)

			if rec.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d", rec.Code)
			}
		})
	}
}

func TestHandleRun_RejectsEmpty(t *testing.T) {
	r := newTestRunner()
	body := `{"task":""}`
	req := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	r.handleRun(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleRun_RejectsWhitespace(t *testing.T) {
	r := newTestRunner()
	body := `{"task":"   "}`
	req := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	r.handleRun(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleRun_RejectsWhileRunning(t *testing.T) {
	r := newTestRunner()
	r.state = StateRunning

	body := `{"task":"do something"}`
	req := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	r.handleRun(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d", rec.Code)
	}
}

func TestHandleRun_AcceptsAfterCompletion(t *testing.T) {
	r := newTestRunner()

	// Simulate a completed session.
	r.mu.Lock()
	r.state = StateDone
	code := 0
	r.exitCode = &code
	now := time.Now()
	r.startedAt = &now
	r.output = []byte("previous output")
	r.plan = []PlanStep{
		{Agent: "test", Description: "test step", Status: "completed"},
	}
	r.currentStep = 1
	r.mu.Unlock()

	// POST /run should be accepted (not 409 Conflict).
	body := `{"task":"second task"}`
	req := httptest.NewRequest("POST", "/run", strings.NewReader(body))
	w := httptest.NewRecorder()
	r.handleRun(w, req)

	if w.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", w.Code, w.Body.String())
	}

	// Previous output should be cleared.
	r.mu.RLock()
	if len(r.output) != 0 {
		t.Errorf("expected output to be cleared, got %d bytes", len(r.output))
	}
	if len(r.plan) != 0 {
		t.Errorf("expected plan to be cleared, got %d steps", len(r.plan))
	}
	if r.currentStep != 0 {
		t.Errorf("expected currentStep to be 0, got %d", r.currentStep)
	}
	r.mu.RUnlock()
}

func TestHandleRun_AcceptsAfterFailure(t *testing.T) {
	r := newTestRunner()

	// Simulate a failed session.
	r.mu.Lock()
	r.state = StateFailed
	code := 1
	r.exitCode = &code
	now := time.Now()
	r.startedAt = &now
	r.output = []byte("error output")
	r.mu.Unlock()

	// POST /run should be accepted (not 409 Conflict).
	body := `{"task":"retry task"}`
	req := httptest.NewRequest("POST", "/run", strings.NewReader(body))
	w := httptest.NewRecorder()
	r.handleRun(w, req)

	if w.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", w.Code, w.Body.String())
	}

	// Previous state should be fully reset.
	r.mu.RLock()
	if r.exitCode != nil {
		t.Errorf("expected exitCode to be nil, got %d", *r.exitCode)
	}
	if len(r.output) != 0 {
		t.Errorf("expected output to be cleared, got %d bytes", len(r.output))
	}
	r.mu.RUnlock()
}

func TestHandleStatus_IncludesPlan(t *testing.T) {
	r := newTestRunner()

	r.mu.Lock()
	r.state = StateRunning
	r.plan = []PlanStep{
		{Agent: "research", Description: "investigate", Status: "completed"},
		{Agent: "code-fix", Description: "fix it", Status: "running"},
		{Agent: "critic", Description: "review", Status: "pending"},
	}
	r.currentStep = 1
	r.mu.Unlock()

	req := httptest.NewRequest("GET", "/status", nil)
	w := httptest.NewRecorder()
	r.handleStatus(w, req)

	var resp StatusResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if len(resp.Plan) != 3 {
		t.Fatalf("expected 3 plan steps, got %d", len(resp.Plan))
	}
	if resp.CurrentStep != 1 {
		t.Errorf("expected current_step=1, got %d", resp.CurrentStep)
	}
	if resp.Plan[0].Status != "completed" {
		t.Errorf("expected step 0 completed, got %s", resp.Plan[0].Status)
	}
}

func TestBuildGooseCmd_NoRecipe(t *testing.T) {
	args := buildGooseCmd(RunRequest{Task: "fix the bug"})

	expected := []string{"goose", "run", "--text", "fix the bug"}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

func TestBuildGooseCmd_WithRecipePath(t *testing.T) {
	recipePath := "projects/agent_platform/goose_agent/image/recipes/ci-debug.yaml"
	task := "do it"
	args := buildGooseCmd(RunRequest{Task: task, RecipePath: recipePath})

	// Expected: goose run --recipe <path> --params task_description=<task> --no-profile
	if len(args) != 7 {
		t.Fatalf("expected 7 args, got %d: %v", len(args), args)
	}
	if args[0] != "goose" || args[1] != "run" {
		t.Fatalf("expected goose run, got %s %s", args[0], args[1])
	}
	if args[2] != "--recipe" {
		t.Fatalf("expected --recipe at args[2], got %s", args[2])
	}
	if args[3] != recipePath {
		t.Fatalf("expected recipe path %q at args[3], got %q", recipePath, args[3])
	}
	if args[4] != "--params" {
		t.Fatalf("expected --params at args[4], got %s", args[4])
	}
	expectedParams := "task_description=" + task
	if args[5] != expectedParams {
		t.Fatalf("expected params %q, got %q", expectedParams, args[5])
	}
	if args[6] != "--no-profile" {
		t.Fatalf("expected --no-profile at args[6], got %s", args[6])
	}
}

func TestParsePlanFromOutput(t *testing.T) {
	output := `Some analysis text here...

` + "```goose-result\n" +
		`type: pipeline
url: https://gist.github.com/jomcgi/abc123
summary: 3-step pipeline to fix auth
pipeline: [{"agent":"research","task":"investigate","condition":"always"},{"agent":"code-fix","task":"fix it","condition":"on success"}]
` + "```\n"

	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if len(steps) != 2 {
		t.Fatalf("expected 2 steps, got %d", len(steps))
	}
	if steps[0].Agent != "research" {
		t.Errorf("step 0 agent: got %q, want %q", steps[0].Agent, "research")
	}
	if steps[0].Task != "investigate" {
		t.Errorf("step 0 task: got %q, want %q", steps[0].Task, "investigate")
	}
	if steps[0].Condition != "always" {
		t.Errorf("step 0 condition: got %q, want %q", steps[0].Condition, "always")
	}
	if steps[1].Agent != "code-fix" {
		t.Errorf("step 1 agent: got %q, want %q", steps[1].Agent, "code-fix")
	}
	if steps[1].Condition != "on success" {
		t.Errorf("step 1 condition: got %q, want %q", steps[1].Condition, "on success")
	}
}

func TestParsePlanFromOutput_NoPipeline(t *testing.T) {
	output := "```goose-result\ntype: report\nsummary: just a report\n```\n"
	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(steps) != 0 {
		t.Errorf("expected 0 steps for non-pipeline result, got %d", len(steps))
	}
}

func TestParsePlanFromOutput_NoBlock(t *testing.T) {
	output := "just some regular output with no goose-result block"
	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(steps) != 0 {
		t.Errorf("expected 0 steps, got %d", len(steps))
	}
}

func TestParsePlanFromOutput_InvalidJSON(t *testing.T) {
	output := "```goose-result\ntype: pipeline\npipeline: not-valid-json\n```\n"
	_, err := parsePlanFromOutput(output)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestParsePlanFromOutput_UsesLastBlock(t *testing.T) {
	// If there are multiple goose-result blocks, use the last one.
	output := "```goose-result\ntype: report\nsummary: first\n```\n" +
		"some more output\n" +
		"```goose-result\ntype: pipeline\npipeline: [{\"agent\":\"final\",\"task\":\"do it\",\"condition\":\"always\"}]\n```\n"
	steps, err := parsePlanFromOutput(output)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if len(steps) != 1 {
		t.Fatalf("expected 1 step, got %d", len(steps))
	}
	if steps[0].Agent != "final" {
		t.Errorf("expected agent 'final', got %q", steps[0].Agent)
	}
}

func TestBuildGooseCmdFromFile(t *testing.T) {
	args := buildGooseCmdFromFile("/recipes/deep-plan.yaml", "fix the bug", "")
	expected := []string{"goose", "run", "--recipe", "/recipes/deep-plan.yaml", "--params", "task_description=fix the bug", "--no-profile"}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Errorf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

func TestBuildGooseCmdFromFile_WithModel(t *testing.T) {
	args := buildGooseCmdFromFile("/recipes/deep-plan.yaml", "fix it", "claude-opus-4-6")
	if len(args) != 9 {
		t.Fatalf("expected 9 args, got %d: %v", len(args), args)
	}
	if args[7] != "--model" || args[8] != "claude-opus-4-6" {
		t.Errorf("expected --model claude-opus-4-6 at end, got %s %s", args[7], args[8])
	}
}

func TestBuildGooseCmd_YAMLHostileTask(t *testing.T) {
	// YAML-special characters in the task are safe because they're passed via
	// --params (CLI arg), not embedded in the recipe YAML.
	hostileTask := `Fix the "auth" bug. Check: key: value. Don't break it.`
	args := buildGooseCmd(RunRequest{
		Task:       hostileTask,
		RecipePath: "recipes/test.yaml",
	})

	// Find --params value.
	for i, arg := range args {
		if arg == "--params" && i+1 < len(args) {
			expected := "task_description=" + hostileTask
			if args[i+1] != expected {
				t.Fatalf("expected params %q, got %q", expected, args[i+1])
			}
			return
		}
	}
	t.Fatal("--params flag not found")
}

package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
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

func TestBuildGooseCmd_NoRecipe(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{Task: "fix the bug"})
	if cleanup != nil {
		t.Fatal("expected nil cleanup for no-recipe mode")
	}

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

func TestBuildGooseCmd_WithRecipe(t *testing.T) {
	recipeYAML := "version: '1.0.0'\ntitle: Test\n"
	task := "do it"
	args, cleanup := buildGooseCmd(RunRequest{Task: task, Recipe: recipeYAML})
	if cleanup == nil {
		t.Fatal("expected cleanup function for temp file")
	}
	defer cleanup()

	// Expected: goose run --recipe <file> --params task_description=<task> --no-profile
	if len(args) != 7 {
		t.Fatalf("expected 7 args, got %d: %v", len(args), args)
	}
	if args[0] != "goose" || args[1] != "run" {
		t.Fatalf("expected goose run, got %s %s", args[0], args[1])
	}
	if args[2] != "--recipe" {
		t.Fatalf("expected --recipe at args[2], got %s", args[2])
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

	// Verify temp file exists and contains recipe content.
	content, err := os.ReadFile(args[3])
	if err != nil {
		t.Fatalf("failed to read temp recipe: %v", err)
	}
	if string(content) != recipeYAML {
		t.Fatalf("expected recipe content %q, got %q", recipeYAML, string(content))
	}
}

func TestBuildGooseCmd_RecipeTempFilePreservesTemplateVars(t *testing.T) {
	recipeYAML := "prompt: '{{ task_description | indent(2) }}'\n"
	args, cleanup := buildGooseCmd(RunRequest{
		Task:   "fix the auth bug",
		Recipe: recipeYAML,
	})
	if cleanup != nil {
		defer cleanup()
	}

	// Read temp file and verify template variables are preserved (not substituted).
	content, err := os.ReadFile(args[3])
	if err != nil {
		t.Fatalf("failed to read temp recipe: %v", err)
	}
	if !strings.Contains(string(content), "task_description") {
		t.Fatal("template variable should be preserved in temp file for goose to handle")
	}
}

func TestBuildGooseCmd_WithModel(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{Task: "plan a pipeline", Model: "claude-opus-4-6"})
	if cleanup != nil {
		defer cleanup()
	}

	expected := []string{"goose", "run", "--text", "plan a pipeline", "--model", "claude-opus-4-6"}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

func TestBuildGooseCmd_WithRecipeAndModel(t *testing.T) {
	args, cleanup := buildGooseCmd(RunRequest{
		Task:   "plan it",
		Recipe: "version: '1.0.0'\ntitle: Test\n",
		Model:  "claude-opus-4-6",
	})
	if cleanup != nil {
		defer cleanup()
	}

	// Should have: goose run --recipe <file> --params ... --no-profile --model claude-opus-4-6
	if len(args) != 9 {
		t.Fatalf("expected 9 args, got %d: %v", len(args), args)
	}
	if args[7] != "--model" || args[8] != "claude-opus-4-6" {
		t.Fatalf("expected --model claude-opus-4-6 at end, got %s %s", args[7], args[8])
	}
}

func TestBuildGooseCmd_EmptyModelOmitted(t *testing.T) {
	args, _ := buildGooseCmd(RunRequest{Task: "fix it"})
	for _, arg := range args {
		if arg == "--model" {
			t.Fatal("--model should not appear when model is empty")
		}
	}
}

func TestBuildGooseCmd_YAMLHostileTask(t *testing.T) {
	// YAML-special characters in the task are safe because they're passed via
	// --params (CLI arg), not embedded in the recipe YAML.
	hostileTask := `Fix the "auth" bug. Check: key: value. Don't break it.`
	args, cleanup := buildGooseCmd(RunRequest{
		Task:   hostileTask,
		Recipe: "version: '1.0.0'\ntitle: Test\n",
	})
	if cleanup != nil {
		defer cleanup()
	}

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

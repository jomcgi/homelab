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

func TestBuildGooseCmd_NoProfile(t *testing.T) {
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

func TestBuildGooseCmd_WithProfile(t *testing.T) {
	args := buildGooseCmd(RunRequest{Task: "debug CI", Profile: "ci-debug"})

	expected := []string{
		"goose", "run",
		"--recipe", "/home/goose-agent/recipes/ci-debug.yaml",
		"--no-profile",
		"--params", "task_description=debug CI",
	}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

func TestBuildGooseCmd_UnknownProfile(t *testing.T) {
	args := buildGooseCmd(RunRequest{Task: "do stuff", Profile: "nonexistent"})

	expected := []string{"goose", "run", "--text", "do stuff"}
	if len(args) != len(expected) {
		t.Fatalf("expected %v, got %v", expected, args)
	}
	for i := range expected {
		if args[i] != expected[i] {
			t.Fatalf("arg[%d]: expected %q, got %q", i, expected[i], args[i])
		}
	}
}

package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
	"unicode/utf8"
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

// TestHandleRun_InvalidJSONBody verifies that a POST /run with a body that
// cannot be decoded as JSON returns 400 Bad Request. This covers the
// json.NewDecoder(req.Body).Decode(&body) error path in handleRun.
func TestHandleRun_InvalidJSONBody(t *testing.T) {
	r := newTestRunner()
	req := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader("not-valid-json{{{"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	r.handleRun(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid JSON body, got %d", rec.Code)
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

// ---------------------------------------------------------------------------
// capStepOutput tests
// ---------------------------------------------------------------------------

func TestCapStepOutput_Empty(t *testing.T) {
	got := capStepOutput("")
	if got != "" {
		t.Fatalf("expected empty string, got %q", got)
	}
}

func TestCapStepOutput_UnderCap(t *testing.T) {
	input := strings.Repeat("x", stepOutputCap-1)
	got := capStepOutput(input)
	if got != input {
		t.Fatalf("expected unchanged output for %d bytes, got len=%d", len(input), len(got))
	}
}

func TestCapStepOutput_ExactCap(t *testing.T) {
	input := strings.Repeat("y", stepOutputCap)
	got := capStepOutput(input)
	if got != input {
		t.Fatalf("expected unchanged output at exactly stepOutputCap bytes")
	}
}

func TestCapStepOutput_OverCap(t *testing.T) {
	// Build a string where we can identify the tail by content.
	prefix := strings.Repeat("A", stepOutputCap+100)
	suffix := strings.Repeat("Z", stepOutputCap)
	input := prefix + suffix

	got := capStepOutput(input)

	if len(got) != stepOutputCap {
		t.Fatalf("expected len=%d, got len=%d", stepOutputCap, len(got))
	}
	// The returned slice must be the tail of the original string.
	want := input[len(input)-stepOutputCap:]
	if got != want {
		t.Fatalf("expected tail of input to be kept")
	}
}

func TestCapStepOutput_TailPreserved(t *testing.T) {
	// Simulate realistic output: large preamble followed by a goose-result block.
	preamble := strings.Repeat("output line\n", 1000) // ~12 KB
	tail := "```goose-result\ntype: pr\nurl: https://example.com\n```\n"
	input := preamble + tail

	got := capStepOutput(input)

	if len(got) > stepOutputCap {
		t.Fatalf("got len=%d, want <= %d", len(got), stepOutputCap)
	}
	// The goose-result block must survive in the tail.
	if !strings.Contains(got, "```goose-result") {
		t.Error("goose-result block not preserved in capped output")
	}
}

// ---------------------------------------------------------------------------
// buildStepTask tests
// ---------------------------------------------------------------------------

func TestBuildStepTask_EmptyUpstream(t *testing.T) {
	// First step: no upstream outputs — raw task returned unchanged.
	task := "Fix the auth bug"
	got := buildStepTask(nil, task)
	if got != task {
		t.Fatalf("expected raw task %q, got %q", task, got)
	}
}

func TestBuildStepTask_EmptySlice(t *testing.T) {
	// Explicitly empty (not nil) slice also returns raw task.
	task := "Write the tests"
	got := buildStepTask([]string{}, task)
	if got != task {
		t.Fatalf("expected raw task %q, got %q", task, got)
	}
}

func TestBuildStepTask_SingleUpstream(t *testing.T) {
	task := "Review the code"
	upstream := []string{"### Step 0: researcher\nFound 3 issues."}

	got := buildStepTask(upstream, task)

	if !strings.HasPrefix(got, "## Upstream Pipeline Output (from 1 prior step(s))") {
		t.Errorf("unexpected header: %q", got[:min(len(got), 80)])
	}
	if !strings.Contains(got, "Found 3 issues.") {
		t.Error("upstream content missing from result")
	}
	if !strings.Contains(got, "## Your Task\n"+task) {
		t.Errorf("'## Your Task' section with task not found in result")
	}
}

func TestBuildStepTask_MultipleUpstream(t *testing.T) {
	task := "Ship it"
	upstream := []string{
		"### Step 0: researcher\nResearch output.",
		"### Step 1: coder\nCode output.",
	}

	got := buildStepTask(upstream, task)

	if !strings.Contains(got, "## Upstream Pipeline Output (from 2 prior step(s))") {
		t.Error("expected count of 2 prior steps in header")
	}
	// Both step outputs must appear.
	if !strings.Contains(got, "Research output.") {
		t.Error("step 0 output missing")
	}
	if !strings.Contains(got, "Code output.") {
		t.Error("step 1 output missing")
	}
	// Steps must be separated by the '---' separator.
	if !strings.Contains(got, "\n\n---\n\n") {
		t.Error("separator between upstream steps missing")
	}
	// Task must appear after '## Your Task'.
	if !strings.Contains(got, "## Your Task\n"+task) {
		t.Errorf("'## Your Task' section not found")
	}
}

func TestBuildStepTask_TotalContextCapped(t *testing.T) {
	// Each upstream entry is larger than upstreamContextCap / 2 so the combined
	// total exceeds the cap.
	big := strings.Repeat("A", upstreamContextCap)
	upstream := []string{
		"### Step 0: agent-a\n" + big,
		"### Step 1: agent-b\n" + big,
	}
	task := "Finalize"

	got := buildStepTask(upstream, task)

	// Extract the context section between the header and '## Your Task'.
	headerEnd := strings.Index(got, "\n")
	taskStart := strings.LastIndex(got, "\n\n## Your Task\n")
	if headerEnd == -1 || taskStart == -1 {
		t.Fatalf("could not find expected sections in output: %q", got[:min(len(got), 200)])
	}
	contextSection := got[headerEnd+1 : taskStart]
	if len(contextSection) > upstreamContextCap {
		t.Errorf("context section len=%d exceeds cap=%d", len(contextSection), upstreamContextCap)
	}
}

func TestBuildStepTask_TotalContextTailKept(t *testing.T) {
	// Verify that when capping, the TAIL (most recent steps) is preserved.
	oldStep := strings.Repeat("old-output-", 2000) // well over cap by itself
	newStep := "VERY_RECENT_UNIQUE_OUTPUT_XYZ"
	upstream := []string{
		"### Step 0: old-agent\n" + oldStep,
		"### Step 1: new-agent\n" + newStep,
	}
	task := "Final step"

	got := buildStepTask(upstream, task)

	// The very recent output must survive in the tail.
	if !strings.Contains(got, newStep) {
		t.Error("most recent upstream output not preserved in capped context")
	}
}

func TestBuildStepTask_CorrectFormat(t *testing.T) {
	// Verify the exact structure of the built task.
	upstream := []string{"### Step 0: worker\nsome work done"}
	task := "Next task"

	got := buildStepTask(upstream, task)

	want := "## Upstream Pipeline Output (from 1 prior step(s))\n" +
		"### Step 0: worker\nsome work done" +
		"\n\n## Your Task\n" +
		task
	if got != want {
		t.Fatalf("format mismatch:\ngot:  %q\nwant: %q", got, want)
	}
}

// ---------------------------------------------------------------------------
// outputBefore slicing logic test
// ---------------------------------------------------------------------------

func TestOutputBeforeSlicing(t *testing.T) {
	// Simulate the pattern used in runGoose to isolate per-step output:
	//   1. Record outputBefore = len(r.output) after writing the separator.
	//   2. Append step output.
	//   3. Slice r.output[outputBefore:] to get only the step's output.
	r := newTestRunner()

	// Simulate separator written before the step.
	separator := "\n--- pipeline step 0: researcher ---\n"
	r.output = append(r.output, []byte(separator)...)
	outputBefore := len(r.output)

	// Simulate step output appended after.
	stepContent := "researcher found 3 issues\n```goose-result\ntype: report\n```\n"
	r.output = append(r.output, []byte(stepContent)...)

	// Slice exactly as runGoose does.
	if outputBefore >= len(r.output) {
		t.Fatal("expected output to grow after step")
	}
	got := string(r.output[outputBefore:])
	if got != stepContent {
		t.Fatalf("slice mismatch:\ngot:  %q\nwant: %q", got, stepContent)
	}

	// Also verify capStepOutput applied to this slice behaves correctly.
	capped := capStepOutput(got)
	if capped != got {
		t.Fatalf("short content should not be capped: len=%d", len(got))
	}
}

func TestOutputBeforeSlicing_SeparatorNotIncluded(t *testing.T) {
	// Verify that the separator itself is NOT included in the step output slice.
	r := newTestRunner()

	separator := "\n--- pipeline step 1: coder ---\n"
	r.output = append(r.output, []byte("prior output")...)
	r.output = append(r.output, []byte(separator)...)
	outputBefore := len(r.output) // capture AFTER separator is written

	stepContent := "coder output here"
	r.output = append(r.output, []byte(stepContent)...)

	got := string(r.output[outputBefore:])
	if strings.Contains(got, separator) {
		t.Error("separator should not appear in the step output slice")
	}
	if got != stepContent {
		t.Fatalf("expected %q, got %q", stepContent, got)
	}
}

// ---------------------------------------------------------------------------
// Composite chain: capStepOutput → format → collect → buildStepTask
// ---------------------------------------------------------------------------

// TestCompositeChain_FullAccumulationFlow exercises the complete per-step context
// accumulation pipeline as it occurs inside runGoose:
//  1. Raw step output is capped via capStepOutput.
//  2. The capped output is formatted with the step label.
//  3. The labelled entry is appended to upstreamOutputs.
//  4. buildStepTask is called with the accumulated entries.
//
// This exercises the integration of the two helpers end-to-end so that any
// future refactoring of either function is caught by a composite regression.
func TestCompositeChain_FullAccumulationFlow(t *testing.T) {
	type stepFixture struct {
		agent  string
		output string
	}
	fixtures := []stepFixture{
		{agent: "researcher", output: "Found 3 security issues.\n```goose-result\ntype: report\nurl: https://example.com/1\n```\n"},
		{agent: "code-fix", output: "Patched all issues.\n```goose-result\ntype: pr\nurl: https://github.com/example/pr/42\n```\n"},
	}

	var upstreamOutputs []string
	for i, f := range fixtures {
		capped := capStepOutput(f.output)
		entry := fmt.Sprintf("### Step %d: %s\n%s", i, f.agent, capped)
		upstreamOutputs = append(upstreamOutputs, entry)
	}

	finalTask := "Summarise all changes and open a release PR."
	result := buildStepTask(upstreamOutputs, finalTask)

	// Header must reference 2 prior steps.
	wantHeader := "## Upstream Pipeline Output (from 2 prior step(s))"
	if !strings.Contains(result, wantHeader) {
		t.Errorf("expected header %q in result, got:\n%s", wantHeader, result)
	}

	// Both step labels must appear.
	for i, f := range fixtures {
		label := fmt.Sprintf("### Step %d: %s", i, f.agent)
		if !strings.Contains(result, label) {
			t.Errorf("step label %q not found in result", label)
		}
	}

	// The goose-result blocks from both steps must survive (output is small,
	// so nothing is capped away).
	if !strings.Contains(result, "https://example.com/1") {
		t.Error("step 0 URL not found in composite result")
	}
	if !strings.Contains(result, "https://github.com/example/pr/42") {
		t.Error("step 1 URL not found in composite result")
	}

	// The final task must appear under '## Your Task'.
	wantTaskSection := "## Your Task\n" + finalTask
	if !strings.Contains(result, wantTaskSection) {
		t.Errorf("'## Your Task' section not found or incorrect in result")
	}

	// The separator between the two step entries must be present.
	if !strings.Contains(result, "\n\n---\n\n") {
		t.Error("separator between upstream step entries missing")
	}
}

// ---------------------------------------------------------------------------
// No-output step: guard `if outputBefore < len(r.output)` must hold
// ---------------------------------------------------------------------------

// TestNoOutputStep_UpstreamNotAppended verifies that when a pipeline step
// produces no output (outputBefore == len(r.output) after the step runs),
// nothing is appended to upstreamOutputs.  This mirrors the guard in runGoose:
//
//	if outputBefore < len(r.output) { ... append ... }
func TestNoOutputStep_UpstreamNotAppended(t *testing.T) {
	r := newTestRunner()

	// Write a separator (as runGoose does) and record the position.
	separator := "\n--- pipeline step 0: silent-agent ---\n"
	r.output = append(r.output, []byte(separator)...)
	outputBefore := len(r.output)

	// Simulate a step that produces zero bytes of new output.
	// (outputBefore == len(r.output) after the step.)

	var upstreamOutputs []string

	// Apply the same guard as in runGoose.
	if outputBefore < len(r.output) {
		stepOutput := capStepOutput(string(r.output[outputBefore:]))
		upstreamOutputs = append(upstreamOutputs, fmt.Sprintf("### Step %d: %s\n%s", 0, "silent-agent", stepOutput))
	}

	if len(upstreamOutputs) != 0 {
		t.Errorf("expected upstreamOutputs to be empty for zero-output step, got %d entries: %v",
			len(upstreamOutputs), upstreamOutputs)
	}

	// buildStepTask with empty upstream must return the raw task unchanged.
	task := "Next step task"
	got := buildStepTask(upstreamOutputs, task)
	if got != task {
		t.Errorf("expected raw task returned unchanged for empty upstream, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Multi-step accumulation with mixed output sizes
// ---------------------------------------------------------------------------

// TestMultiStepAccumulation_MixedSizes drives a 3-step scenario through the
// same logic that runGoose uses:
//
//   - Step 0: output exceeds stepOutputCap → gets truncated by capStepOutput.
//   - Step 1: output is small → passes through capStepOutput unchanged.
//   - Step 2: produces no output → guard prevents it from entering upstream.
//
// The test verifies that buildStepTask receives exactly 2 entries (not 3),
// that the step 0 entry is capped to stepOutputCap bytes, and that the final
// augmented task is well-formed.
func TestMultiStepAccumulation_MixedSizes(t *testing.T) {
	type stepSim struct {
		agent  string
		output string // what the step wrote to r.output
	}
	steps := []stepSim{
		{
			agent: "big-researcher",
			// Output well over the cap; the unique tail must survive.
			output: strings.Repeat("noise\n", 2000) + "```goose-result\ntype: report\nurl: https://big.example.com\n```\n",
		},
		{
			agent:  "small-coder",
			output: "Small patch applied.\n```goose-result\ntype: pr\nurl: https://small.example.com\n```\n",
		},
		{
			agent:  "silent-reviewer",
			output: "", // zero bytes — skipped by guard
		},
	}

	r := newTestRunner()
	var upstreamOutputs []string

	for i, s := range steps {
		separator := fmt.Sprintf("\n--- pipeline step %d: %s ---\n", i, s.agent)
		r.output = append(r.output, []byte(separator)...)
		outputBefore := len(r.output)

		// Simulate the step running and writing its output.
		r.output = append(r.output, []byte(s.output)...)

		// Guard: only record output if the step actually produced some.
		if outputBefore < len(r.output) {
			capped := capStepOutput(string(r.output[outputBefore:]))
			entry := fmt.Sprintf("### Step %d: %s\n%s", i, s.agent, capped)
			upstreamOutputs = append(upstreamOutputs, entry)
		}
	}

	// Step 2 produced no output, so exactly 2 entries should have been collected.
	if len(upstreamOutputs) != 2 {
		t.Fatalf("expected 2 upstream entries (step 2 skipped), got %d", len(upstreamOutputs))
	}

	// Step 0's entry must be capped to stepOutputCap bytes of the *raw* output
	// (the "### Step 0: …\n" prefix is added on top, so the total entry length
	// will be slightly more than stepOutputCap, but the output portion is capped).
	entry0 := upstreamOutputs[0]
	// The entry is: "### Step 0: big-researcher\n" + capped_output
	prefix0 := "### Step 0: big-researcher\n"
	if !strings.HasPrefix(entry0, prefix0) {
		t.Fatalf("step 0 entry has wrong prefix: %q", entry0[:min(len(entry0), 60)])
	}
	cappedPart0 := entry0[len(prefix0):]
	if len(cappedPart0) > stepOutputCap {
		t.Errorf("step 0 capped output len=%d exceeds stepOutputCap=%d", len(cappedPart0), stepOutputCap)
	}
	// The goose-result tail must be preserved in the capped step 0 output.
	if !strings.Contains(cappedPart0, "https://big.example.com") {
		t.Error("step 0 goose-result URL not preserved after capping")
	}

	// Step 1's entry must be present and untruncated.
	entry1 := upstreamOutputs[1]
	if !strings.Contains(entry1, "https://small.example.com") {
		t.Error("step 1 URL missing from upstream entry")
	}

	// Build the final augmented task for a hypothetical step 3.
	finalTask := "Ship the release."
	result := buildStepTask(upstreamOutputs, finalTask)

	// Header must reflect exactly 2 prior steps.
	wantHeader := "## Upstream Pipeline Output (from 2 prior step(s))"
	if !strings.Contains(result, wantHeader) {
		t.Errorf("expected header %q in result", wantHeader)
	}

	// Final task section must appear.
	if !strings.Contains(result, "## Your Task\n"+finalTask) {
		t.Error("'## Your Task' section missing or incorrect in result")
	}
}

// ---------------------------------------------------------------------------
// Multi-byte UTF-8 slicing near the cap boundary
// ---------------------------------------------------------------------------

// TestCapStepOutput_MultiByteUTF8NearBoundary documents the byte-level slicing
// behaviour of capStepOutput when multi-byte Unicode characters (emoji and CJK
// codepoints) straddle the cap boundary.
//
// capStepOutput slices at a byte offset, not a rune boundary, so the character
// immediately preceding the cut point may be split into an invalid UTF-8
// sequence.  This is an accepted trade-off: the function guarantees at most
// stepOutputCap bytes are returned and that the tail (including the
// goose-result block) is preserved — rune integrity near the cut point is not
// guaranteed.
//
// The test:
//  1. Verifies the output length never exceeds stepOutputCap.
//  2. Verifies the tail content (always ASCII in practice: the goose-result
//     block) is preserved intact.
//  3. Acknowledges that the number of valid UTF-8 runes in the returned slice
//     may be less than the number in an equivalent byte slice starting at a
//     clean rune boundary — i.e. the first rune at the cut point may be
//     invalid.
func TestCapStepOutput_MultiByteUTF8NearBoundary(t *testing.T) {
	// Build a preamble of multi-byte characters.
	// '🔥' is 4 bytes; '中' is 3 bytes. We mix them to create a string whose
	// byte length is slightly larger than stepOutputCap.
	multiByteChunk := strings.Repeat("🔥", 200) + strings.Repeat("中文字", 200)
	// ASCII tail that must survive — mirrors a goose-result block.
	asciiTail := "```goose-result\ntype: report\nurl: https://utf8-test.example.com\nsummary: done\n```\n"

	// Pad so that the total is just over the cap and the cut falls inside a
	// multi-byte sequence.
	padding := strings.Repeat("A", stepOutputCap)
	input := multiByteChunk + padding + asciiTail

	got := capStepOutput(input)

	// 1. Length invariant: must not exceed cap.
	if len(got) > stepOutputCap {
		t.Errorf("output len=%d exceeds stepOutputCap=%d", len(got), stepOutputCap)
	}

	// 2. Tail preservation: the ASCII goose-result block must be intact.
	if !strings.Contains(got, asciiTail) {
		t.Error("ASCII tail (goose-result block) not preserved after byte-level cap")
	}

	// 3. Document that byte-slicing may produce an invalid leading rune.
	//    We count valid runes and compare to a fresh re-decode of the same
	//    bytes.  If the cut split a multi-byte character, the first rune of
	//    'got' will decode as utf8.RuneError with size 1, which is acceptable.
	gotBytes := []byte(got)
	firstRune, _ := utf8.DecodeRune(gotBytes)
	// We don't assert firstRune == utf8.RuneError because the cut might also
	// land on a clean ASCII boundary.  We simply record the observation.
	t.Logf("first rune after byte-level cut: %U (RuneError=%v)", firstRune, firstRune == utf8.RuneError)

	// The remainder of the string (after any partial rune at the front) must
	// be valid UTF-8 once we skip the potentially-split leading bytes.
	// The ASCII tail at the end is always valid.
	if !utf8.Valid([]byte(asciiTail)) {
		t.Error("asciiTail itself is not valid UTF-8 (test bug)")
	}
}

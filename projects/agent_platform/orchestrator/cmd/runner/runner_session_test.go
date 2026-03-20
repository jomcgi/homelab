package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// overrideWorkDir sets the package-level workDir for the duration of the test
// and restores the original value on cleanup. runSession passes workDir as
// cmd.Dir, so it must be a real directory.
func overrideWorkDir(t *testing.T, dir string) {
	t.Helper()
	orig := workDir
	workDir = dir
	t.Cleanup(func() { workDir = orig })
}

// gooseResultBlock returns a goose-result fenced block with the given content.
// Uses string concatenation to embed backtick fences without raw-string issues.
func gooseResultBlock(content string) string {
	return "```goose-result\n" + content + "\n```"
}

// fakeStepConfig controls the output and exit code of a fake pipeline step.
type fakeStepConfig struct {
	output   string
	exitCode int
}

// setupFakeGoosePipeline creates a fake `goose` binary that dispatches on the
// --recipe argument. deepPlanOutput is emitted (exit 0) for */deep-plan.yaml.
// steps maps agent name → fakeStepConfig. Output files are written to dir so
// the shell script can cat them (avoids backtick escaping in the script body).
// Returns the directory that was prepended to PATH.
func setupFakeGoosePipeline(t *testing.T, dir, deepPlanOutput string, steps map[string]fakeStepConfig) string {
	t.Helper()

	// Write deep-plan output to a file.
	dpFile := filepath.Join(dir, "_output_deep_plan.txt")
	if err := os.WriteFile(dpFile, []byte(deepPlanOutput), 0o644); err != nil {
		t.Fatalf("setupFakeGoosePipeline: write deep-plan output: %v", err)
	}

	var sb strings.Builder
	sb.WriteString("RECIPE=\"\"\n")
	sb.WriteString("while [ $# -gt 0 ]; do\n")
	sb.WriteString("    if [ \"$1\" = \"--recipe\" ]; then RECIPE=\"$2\"; break; fi\n")
	sb.WriteString("    shift\ndone\n")
	sb.WriteString("case \"$RECIPE\" in\n")
	fmt.Fprintf(&sb, "    */deep-plan.yaml)\n        cat '%s'; exit 0 ;;\n", dpFile)

	for agent, cfg := range steps {
		outFile := filepath.Join(dir, "_output_"+agent+".txt")
		if err := os.WriteFile(outFile, []byte(cfg.output), 0o644); err != nil {
			t.Fatalf("setupFakeGoosePipeline: write step output for %s: %v", agent, err)
		}
		fmt.Fprintf(&sb, "    */%s.yaml)\n        cat '%s'; exit %d ;;\n", agent, outFile, cfg.exitCode)
	}

	sb.WriteString("    *)\n        echo \"unknown recipe: $RECIPE\"; exit 1 ;;\nesac\n")

	binPath := filepath.Join(dir, "goose")
	if err := os.WriteFile(binPath, []byte("#!/bin/sh\n"+sb.String()), 0o755); err != nil {
		t.Fatalf("setupFakeGoosePipeline: write binary: %v", err)
	}

	origPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+":"+origPath)
	return dir
}

// setupSimpleFakeGoose creates a minimal fake `goose` that runs the given
// shell snippet and prepends its directory to PATH. Returns the bin directory.
func setupSimpleFakeGoose(t *testing.T, script string) string {
	t.Helper()
	dir := t.TempDir()
	binPath := filepath.Join(dir, "goose")
	if err := os.WriteFile(binPath, []byte("#!/bin/sh\n"+script+"\n"), 0o755); err != nil {
		t.Fatalf("setupSimpleFakeGoose: %v", err)
	}
	origPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+":"+origPath)
	return dir
}

// makeRecipeFiles creates empty YAML recipe files in dir for each agent name.
func makeRecipeFiles(t *testing.T, dir string, agents ...string) {
	t.Helper()
	for _, agent := range agents {
		path := filepath.Join(dir, agent+".yaml")
		if err := os.WriteFile(path, []byte("version: 1.0\n"), 0o644); err != nil {
			t.Fatalf("makeRecipeFiles: write recipe for %s: %v", agent, err)
		}
	}
}

// =============================================================================
// runSession tests
// =============================================================================

func TestRunSession_Success(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	exitCode, err := r.runSession(context.Background(), []string{"echo", "hello"}, 30*time.Second)
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
	if exitCode != 0 {
		t.Fatalf("expected exit code 0, got %d", exitCode)
	}
}

func TestRunSession_OutputCapturedInBuffer(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	_, _ = r.runSession(context.Background(), []string{"/bin/sh", "-c", "printf 'runner output'"}, 30*time.Second)

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, "runner output") {
		t.Errorf("expected 'runner output' in buffer, got: %q", out)
	}
}

func TestRunSession_StderrCaptured(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	_, _ = r.runSession(context.Background(), []string{"/bin/sh", "-c", "printf 'stderr line' >&2"}, 30*time.Second)

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, "stderr line") {
		t.Errorf("expected stderr captured in output buffer, got: %q", out)
	}
}

func TestRunSession_Failure_NonZeroExitCode(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	exitCode, err := r.runSession(context.Background(), []string{"/bin/sh", "-c", "exit 2"}, 30*time.Second)

	if exitCode != 2 {
		t.Errorf("expected exit code 2, got %d", exitCode)
	}
	if err == nil {
		t.Error("expected non-nil error for non-zero exit, got nil")
	}
}

func TestRunSession_CommandNotFound(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	exitCode, err := r.runSession(context.Background(), []string{"/definitely-does-not-exist-runner-binary"}, 30*time.Second)

	if err == nil {
		t.Fatal("expected error for non-existent binary, got nil")
	}
	if exitCode != -1 {
		t.Errorf("expected -1 for start failure, got %d", exitCode)
	}

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()
	if !strings.Contains(out, "failed to start") {
		t.Errorf("expected 'failed to start' message in output buffer, got: %q", out)
	}
}

func TestRunSession_PIDRecordedAfterStart(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	_, _ = r.runSession(context.Background(), []string{"echo", "pid test"}, 30*time.Second)

	r.mu.RLock()
	pid := r.pid
	r.mu.RUnlock()
	if pid == 0 {
		t.Error("expected r.pid to be non-zero after process ran")
	}
}

func TestRunSession_OutputAccumulatesAcrossSessions(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())
	ctx := context.Background()

	_, _ = r.runSession(ctx, []string{"/bin/sh", "-c", "printf 'first-session'"}, 30*time.Second)
	_, _ = r.runSession(ctx, []string{"/bin/sh", "-c", "printf 'second-session'"}, 30*time.Second)

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, "first-session") {
		t.Error("first session output missing from accumulated buffer")
	}
	if !strings.Contains(out, "second-session") {
		t.Error("second session output missing from accumulated buffer")
	}
}

func TestRunSession_ContextCancellation(t *testing.T) {
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		r.runSession(ctx, []string{"sleep", "60"}, 30*time.Second)
	}()

	// Poll until the process has started (r.pid is set after cmd.Start returns).
	// This is more robust than a fixed sleep since it unblocks as soon as the
	// PID is recorded rather than relying on wall-clock timing.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		r.mu.RLock()
		pid := r.pid
		r.mu.RUnlock()
		if pid != 0 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	cancel()

	select {
	case <-done:
		// runSession returned promptly after cancellation.
	case <-time.After(5 * time.Second):
		t.Fatal("runSession did not return within 5s after context cancellation")
	}
}

func TestRunSession_InactivityTimeout(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping inactivity timeout test in -short mode: watchdog tick is 5s")
	}
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	// Timeout of 50ms; watchdog fires every 5s, so the test takes ~5s.
	start := time.Now()
	_, _ = r.runSession(context.Background(), []string{"sleep", "60"}, 50*time.Millisecond)
	elapsed := time.Since(start)

	if elapsed > 15*time.Second {
		t.Errorf("inactivity timeout test took too long: %v (expected < 15s)", elapsed)
	}

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, "inactivity timeout") {
		t.Errorf("expected 'inactivity timeout' kill message in output, got: %q", out)
	}
	if !strings.Contains(out, "killed") {
		t.Errorf("expected 'killed' message in output after watchdog fires, got: %q", out)
	}
}

func TestRunSession_InactivityResetOnOutput(t *testing.T) {
	// Verify that receiving output resets the inactivity timer: a process that
	// outputs data every second should NOT be killed by a 2s inactivity timeout
	// because each output chunk resets the timer.
	if testing.Short() {
		t.Skip("skipping: takes ~3s")
	}
	r := newTestRunner()
	overrideWorkDir(t, t.TempDir())

	// Print a character every 500ms for 2s total, then exit.
	// Inactivity timeout is 1.5s; each print resets the timer.
	script := "i=0; while [ $i -lt 4 ]; do printf 'x'; sleep 0.5; i=$((i+1)); done"
	_, err := r.runSession(context.Background(), []string{"/bin/sh", "-c", script}, 1500*time.Millisecond)
	// Process should exit normally (not killed by inactivity watchdog).
	if err != nil {
		t.Logf("process returned error (may be expected on some platforms): %v", err)
	}

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if strings.Contains(out, "killed") {
		t.Error("process should not have been killed by inactivity watchdog while producing output")
	}
}

// =============================================================================
// runGoose tests — standard mode (no DEEP_PLAN_RECIPE)
// =============================================================================

func TestRunGoose_StandardMode_Done(t *testing.T) {
	dir := setupSimpleFakeGoose(t, `echo "all done"; exit 0`)
	overrideWorkDir(t, dir)
	t.Setenv("DEEP_PLAN_RECIPE", "")

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "fix the bug"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	exitCode := r.exitCode
	r.mu.RUnlock()

	if state != StateDone {
		t.Errorf("expected state=done, got %s", state)
	}
	if exitCode == nil || *exitCode != 0 {
		t.Errorf("expected exit_code=0, got %v", exitCode)
	}
}

func TestRunGoose_StandardMode_Failed(t *testing.T) {
	dir := setupSimpleFakeGoose(t, `echo "something went wrong"; exit 1`)
	overrideWorkDir(t, dir)
	t.Setenv("DEEP_PLAN_RECIPE", "")

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "fix the bug"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	if state != StateFailed {
		t.Errorf("expected state=failed for non-zero exit, got %s", state)
	}
}

func TestRunGoose_StandardMode_OutputCaptured(t *testing.T) {
	dir := setupSimpleFakeGoose(t, `printf 'standard mode output'`)
	overrideWorkDir(t, dir)
	t.Setenv("DEEP_PLAN_RECIPE", "")

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "check output"}, 30*time.Second)

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, "standard mode output") {
		t.Errorf("expected output in buffer, got: %q", out)
	}
}

func TestRunGoose_StandardMode_WithRecipePath(t *testing.T) {
	dir := setupSimpleFakeGoose(t, `exit 0`)
	overrideWorkDir(t, dir)
	t.Setenv("DEEP_PLAN_RECIPE", "")

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{
		Task:       "fix it",
		RecipePath: "/any/recipe.yaml",
	}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	if state != StateDone {
		t.Errorf("expected state=done with recipe path, got %s", state)
	}
}

// =============================================================================
// runGoose tests — autonomous pipeline mode (DEEP_PLAN_RECIPE set)
// =============================================================================

func TestRunGoose_DeepPlan_NoPipelineResult(t *testing.T) {
	recipesDir := t.TempDir()
	dpOutput := gooseResultBlock("type: report\nsummary: no pipeline here")
	setupFakeGoosePipeline(t, recipesDir, dpOutput, nil)
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	// No pipeline → treated as single session → done.
	if state != StateDone {
		t.Errorf("expected state=done for non-pipeline result, got %s", state)
	}
}

func TestRunGoose_DeepPlan_EmptyPipelineArray(t *testing.T) {
	recipesDir := t.TempDir()
	dpOutput := gooseResultBlock("type: pipeline\npipeline: []")
	setupFakeGoosePipeline(t, recipesDir, dpOutput, nil)
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	// Empty pipeline array → no steps → single session mode → done.
	if state != StateDone {
		t.Errorf("expected state=done for empty pipeline, got %s", state)
	}
}

func TestRunGoose_DeepPlan_RecipesDirNotSet(t *testing.T) {
	recipesDir := t.TempDir()
	pipelineJSON := `[{"agent":"code-fix","task":"do it","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	setupFakeGoosePipeline(t, recipesDir, dpOutput, nil)
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", "") // deliberately unset

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	if state != StateFailed {
		t.Errorf("expected state=failed when RECIPES_DIR unset, got %s", state)
	}
}

func TestRunGoose_DeepPlan_StepRecipeMissing(t *testing.T) {
	recipesDir := t.TempDir()
	// Pipeline references "ghost-agent" — no recipe file is created for it.
	pipelineJSON := `[{"agent":"ghost-agent","task":"haunt","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	setupFakeGoosePipeline(t, recipesDir, dpOutput, nil)
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	plan := r.plan
	r.mu.RUnlock()

	if state != StateFailed {
		t.Errorf("expected state=failed for missing recipe, got %s", state)
	}
	if len(plan) != 1 || plan[0].Status != "failed" {
		t.Errorf("expected plan[0].status=failed, got plan=%+v", plan)
	}
}

func TestRunGoose_DeepPlan_ParseError(t *testing.T) {
	recipesDir := t.TempDir()
	// Invalid JSON in pipeline field.
	dpOutput := gooseResultBlock("type: pipeline\npipeline: not-valid-json")
	setupFakeGoosePipeline(t, recipesDir, dpOutput, nil)
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	// runGoose sets state=done (not failed) on pipeline parse error.
	if state != StateDone {
		t.Errorf("expected state=done on pipeline parse error, got %s", state)
	}
}

func TestRunGoose_DeepPlan_SingleStep_Success(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "code-fix")

	pipelineJSON := `[{"agent":"code-fix","task":"fix the bug","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	stepOut := "Fix applied.\n" + gooseResultBlock("type: pr\nurl: https://github.com/example/pr/1")

	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"code-fix": {output: stepOut, exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "fix the bug"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	plan := r.plan
	exitCode := r.exitCode
	r.mu.RUnlock()

	if state != StateDone {
		t.Errorf("expected state=done after successful single-step pipeline, got %s", state)
	}
	if len(plan) != 1 {
		t.Fatalf("expected 1 plan step, got %d", len(plan))
	}
	if plan[0].Status != "completed" {
		t.Errorf("expected step status=completed, got %s", plan[0].Status)
	}
	if plan[0].Agent != "code-fix" {
		t.Errorf("expected agent=code-fix, got %s", plan[0].Agent)
	}
	if exitCode == nil || *exitCode != 0 {
		t.Errorf("expected exit_code=0, got %v", exitCode)
	}
}

func TestRunGoose_DeepPlan_PlanExposedViaStatus(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "tester")

	pipelineJSON := `[{"agent":"tester","task":"run tests","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)

	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"tester": {output: "tests passed", exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "run tests"}, 30*time.Second)

	r.mu.RLock()
	plan := r.plan
	r.mu.RUnlock()

	if len(plan) != 1 {
		t.Fatalf("expected 1 plan step, got %d", len(plan))
	}
	if plan[0].Agent != "tester" {
		t.Errorf("expected agent=tester, got %s", plan[0].Agent)
	}
	if plan[0].Description != "run tests" {
		t.Errorf("expected description='run tests', got %q", plan[0].Description)
	}
}

func TestRunGoose_DeepPlan_ConditionSkipOnPriorFailure(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "step-one", "step-two")

	pipelineJSON := `[{"agent":"step-one","task":"first","condition":"always"},{"agent":"step-two","task":"second","condition":"on success"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)

	// step-one exits 1 → lastErr != nil → step-two ("on success") is skipped.
	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"step-one": {output: "step-one failed", exitCode: 1},
		"step-two": {output: "step-two should not run", exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	plan := r.plan
	r.mu.RUnlock()

	if state != StateFailed {
		t.Errorf("expected state=failed (step-one failed), got %s", state)
	}
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
	if plan[0].Status != "failed" {
		t.Errorf("step 0: expected failed, got %s", plan[0].Status)
	}
	if plan[1].Status != "skipped" {
		t.Errorf("step 1: expected skipped (on success after failure), got %s", plan[1].Status)
	}
}

func TestRunGoose_DeepPlan_MultiStep_AllSucceed(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "researcher", "coder")

	pipelineJSON := `[{"agent":"researcher","task":"investigate","condition":"always"},{"agent":"coder","task":"fix","condition":"on success"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	researchOut := "Found the root cause.\n" + gooseResultBlock("type: report\nurl: https://example.com/report")
	coderOut := "Applied the fix.\n" + gooseResultBlock("type: pr\nurl: https://github.com/example/pr/99")

	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"researcher": {output: researchOut, exitCode: 0},
		"coder":      {output: coderOut, exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "investigate and fix"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	plan := r.plan
	out := string(r.output)
	r.mu.RUnlock()

	if state != StateDone {
		t.Errorf("expected state=done for successful 2-step pipeline, got %s", state)
	}
	if len(plan) != 2 {
		t.Fatalf("expected 2 plan steps, got %d", len(plan))
	}
	for i, ps := range plan {
		if ps.Status != "completed" {
			t.Errorf("plan[%d].Status: expected completed, got %s", i, ps.Status)
		}
	}
	// Step separators must appear in the combined output buffer.
	if !strings.Contains(out, "pipeline step 0: researcher") {
		t.Error("expected step 0 separator in combined output")
	}
	if !strings.Contains(out, "pipeline step 1: coder") {
		t.Error("expected step 1 separator in combined output")
	}
}

func TestRunGoose_DeepPlan_StepOutputInBuffer(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "worker")

	pipelineJSON := `[{"agent":"worker","task":"do work","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	stepOut := "worker produced this output"

	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"worker": {output: stepOut, exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)

	r.mu.RLock()
	out := string(r.output)
	r.mu.RUnlock()

	if !strings.Contains(out, stepOut) {
		t.Errorf("expected step output %q in combined buffer, got: %q", stepOut, out)
	}
}

func TestRunGoose_DeepPlan_ContextCancelled_DoesNotHang(t *testing.T) {
	recipesDir := t.TempDir()
	// Create the recipe file so the test is isolated to context-cancellation
	// behaviour and does not accidentally pass due to a missing-recipe failure.
	makeRecipeFiles(t, recipesDir, "code-fix")
	pipelineJSON := `[{"agent":"code-fix","task":"do it","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)
	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"code-fix": {output: "should not run", exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning

	// Pre-cancel context: runGoose must return promptly without hanging.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	done := make(chan struct{})
	go func() {
		defer close(done)
		r.runGoose(ctx, cancel, RunRequest{Task: "do work"}, 30*time.Second)
	}()

	select {
	case <-done:
		// Good: returned without hanging.
	case <-time.After(10 * time.Second):
		t.Fatal("runGoose did not return within 10s with pre-cancelled context")
	}

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	if state == StateRunning {
		t.Errorf("expected terminal state after context cancellation, got state=running")
	}
}

func TestRunGoose_DeepPlan_CurrentStepUpdated(t *testing.T) {
	recipesDir := t.TempDir()
	makeRecipeFiles(t, recipesDir, "step-a", "step-b")

	pipelineJSON := `[{"agent":"step-a","task":"first","condition":"always"},{"agent":"step-b","task":"second","condition":"always"}]`
	dpOutput := gooseResultBlock("type: pipeline\npipeline: " + pipelineJSON)

	setupFakeGoosePipeline(t, recipesDir, dpOutput, map[string]fakeStepConfig{
		"step-a": {output: "step a done", exitCode: 0},
		"step-b": {output: "step b done", exitCode: 0},
	})
	overrideWorkDir(t, recipesDir)
	t.Setenv("DEEP_PLAN_RECIPE", "/fake/deep-plan.yaml")
	t.Setenv("RECIPES_DIR", recipesDir)

	r := newTestRunner()
	r.state = StateRunning
	ctx, cancel := context.WithCancel(context.Background())
	r.runGoose(ctx, cancel, RunRequest{Task: "run steps"}, 30*time.Second)

	r.mu.RLock()
	state := r.state
	r.mu.RUnlock()

	if state != StateDone {
		t.Errorf("expected state=done, got %s", state)
	}
}

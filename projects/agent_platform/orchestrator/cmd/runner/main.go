// Package main implements the agent-runner HTTP server.
//
// The runner replaces "sleep infinity" as the goose container entrypoint.
// It manages goose as a child process, captures output to memory, and
// exposes status/output over HTTP so the orchestrator can communicate
// without fragile SPDY exec connections.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// State represents the lifecycle state of the runner.
type State string

const (
	StateIdle    State = "idle"
	StateRunning State = "running"
	StateDone    State = "done"
	StateFailed  State = "failed"
)

// defaultPort is the HTTP listen port when RUNNER_PORT is not set.
const defaultPort = "8081"

// defaultInactivityTimeout is used when a request omits inactivity_timeout.
const defaultInactivityTimeout = 30 * time.Minute

// workDir is the working directory for goose processes.
// It is read from the GOOSE_WORKSPACE env var injected by the SandboxTemplate
// (set to /workspace/<repoName>). Falls back to /workspace/homelab for
// backwards compatibility with existing deployments that pre-date this env var.
var workDir = func() string {
	if ws := os.Getenv("GOOSE_WORKSPACE"); ws != "" {
		return ws
	}
	return "/workspace/homelab"
}()

// maxOutputBytes caps the in-memory output buffer. When exceeded, the buffer
// is truncated to the last maxOutputBytes bytes (keeping the tail).
const maxOutputBytes = 50 * 1024 * 1024 // 50MB

// RunRequest is the JSON body for POST /run.
type RunRequest struct {
	Task              string `json:"task"`
	RecipePath        string `json:"recipe_path,omitempty"`
	InactivityTimeout int    `json:"inactivity_timeout,omitempty"` // seconds
}

// PlanStep represents one step in the autonomous pipeline plan.
type PlanStep struct {
	Agent       string `json:"agent"`
	Description string `json:"description"`
	Status      string `json:"status"` // pending, running, completed, failed, skipped
}

// StatusResponse is returned by GET /status.
type StatusResponse struct {
	State       State      `json:"state"`
	PID         int        `json:"pid,omitempty"`
	ExitCode    *int       `json:"exit_code,omitempty"`
	StartedAt   *time.Time `json:"started_at,omitempty"`
	Plan        []PlanStep `json:"plan,omitempty"`
	CurrentStep int        `json:"current_step"`
}

// runner holds all mutable state for the running goose process.
type runner struct {
	mu          sync.RWMutex
	state       State
	pid         int
	exitCode    *int
	startedAt   *time.Time
	output      []byte
	cancel      context.CancelFunc
	plan        []PlanStep
	currentStep int
}

func newRunner() *runner {
	return &runner{state: StateIdle}
}

// handleHealth is the liveness probe endpoint.
func (r *runner) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, `{"status":"ok"}`)
}

// handleStatus returns the current runner state.
func (r *runner) handleStatus(w http.ResponseWriter, _ *http.Request) {
	r.mu.RLock()
	resp := StatusResponse{
		State:       r.state,
		PID:         r.pid,
		ExitCode:    r.exitCode,
		StartedAt:   r.startedAt,
		Plan:        r.plan,
		CurrentStep: r.currentStep,
	}
	r.mu.RUnlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

// handleOutput returns captured output from the given byte offset.
func (r *runner) handleOutput(w http.ResponseWriter, req *http.Request) {
	offset := 0
	if s := req.URL.Query().Get("offset"); s != "" {
		n, err := strconv.Atoi(s)
		if err != nil || n < 0 {
			http.Error(w, "invalid offset", http.StatusBadRequest)
			return
		}
		offset = n
	}

	r.mu.RLock()
	total := len(r.output)
	var chunk []byte
	if offset < total {
		chunk = make([]byte, total-offset)
		copy(chunk, r.output[offset:])
	}
	r.mu.RUnlock()

	w.Header().Set("Content-Type", "text/plain")
	w.Header().Set("X-Output-Offset", strconv.Itoa(total))
	w.Write(chunk)
}

// handleRun starts a new goose process.
func (r *runner) handleRun(w http.ResponseWriter, req *http.Request) {
	var body RunRequest
	if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.Task) == "" {
		http.Error(w, "task is required", http.StatusBadRequest)
		return
	}

	r.mu.Lock()
	if r.state == StateRunning {
		r.mu.Unlock()
		http.Error(w, "task already running", http.StatusConflict)
		return
	}

	// Reset state for new task.
	now := time.Now()
	r.state = StateRunning
	r.pid = 0
	r.exitCode = nil
	r.startedAt = &now
	r.output = nil
	r.plan = nil
	r.currentStep = 0

	// Cancel any previous context (shouldn't be running, but be safe).
	if r.cancel != nil {
		r.cancel()
	}
	ctx, cancel := context.WithCancel(context.Background())
	r.cancel = cancel
	r.mu.Unlock()

	timeout := defaultInactivityTimeout
	if body.InactivityTimeout > 0 {
		timeout = time.Duration(body.InactivityTimeout) * time.Second
	}

	go r.runGoose(ctx, cancel, body, timeout)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	fmt.Fprint(w, `{"status":"accepted"}`)
}

// parsedStep is the raw step from the goose-result pipeline JSON.
type parsedStep struct {
	Agent     string `json:"agent"`
	Task      string `json:"task"`
	Condition string `json:"condition"`
}

// parsePlanFromOutput extracts pipeline steps from a goose-result block.
// Returns empty slice (not error) if the result type is not "pipeline".
func parsePlanFromOutput(output string) ([]parsedStep, error) {
	const startMarker = "```goose-result\n"
	const endMarker = "\n```"

	lastStart := strings.LastIndex(output, startMarker)
	if lastStart == -1 {
		return nil, nil
	}
	content := output[lastStart+len(startMarker):]
	endIdx := strings.Index(content, endMarker)
	if endIdx == -1 {
		return nil, nil
	}
	content = content[:endIdx]

	var resultType string
	var pipelineJSON string
	for _, line := range strings.Split(content, "\n") {
		key, val, ok := strings.Cut(line, ": ")
		if !ok {
			continue
		}
		switch strings.TrimSpace(key) {
		case "type":
			resultType = strings.TrimSpace(val)
		case "pipeline":
			pipelineJSON = strings.TrimSpace(val)
		}
	}

	if resultType != "pipeline" || pipelineJSON == "" {
		return nil, nil
	}

	var steps []parsedStep
	if err := json.Unmarshal([]byte(pipelineJSON), &steps); err != nil {
		return nil, fmt.Errorf("parsing pipeline JSON: %w", err)
	}
	return steps, nil
}

// buildGooseCmdFromFile constructs goose command arguments using a recipe file
// path directly (no temp file needed). Used for autonomous pipeline execution.
func buildGooseCmdFromFile(recipePath, task, model string) []string {
	args := []string{
		"goose", "run",
		"--recipe", recipePath,
		"--params", "task_description=" + task,
		"--no-profile",
	}
	if model != "" {
		args = append(args, "--model", model)
	}
	return args
}

// buildGooseCmd constructs the goose command arguments.
// When a recipe path is provided, it passes it directly to goose along with
// the task via --params so goose's MiniJinja engine handles template substitution.
func buildGooseCmd(body RunRequest) []string {
	if body.RecipePath != "" {
		return []string{
			"goose", "run",
			"--recipe", body.RecipePath,
			"--params", "task_description=" + body.Task,
			"--no-profile",
		}
	}
	return []string{"goose", "run", "--text", body.Task}
}

// runSession spawns a single goose process with the given args, captures output,
// and manages the inactivity watchdog. Returns the exit code and any error.
// Output is appended to r.output (accumulates across sessions).
func (r *runner) runSession(ctx context.Context, args []string, inactivityTimeout time.Duration) (int, error) {
	cmd := exec.CommandContext(ctx, args[0], args[1:]...)
	cmd.Dir = workDir

	// Set up output capture: goose stdout+stderr -> pipe -> tee to os.Stdout + memory buffer.
	pr, pw := io.Pipe()
	cmd.Stdout = pw
	cmd.Stderr = pw

	if err := cmd.Start(); err != nil {
		msg := fmt.Sprintf("failed to start goose: %v\n", err)
		log.Print(msg)
		r.mu.Lock()
		r.output = append(r.output, []byte(msg)...)
		r.mu.Unlock()
		pw.Close()
		return -1, err
	}

	r.mu.Lock()
	r.pid = cmd.Process.Pid
	r.mu.Unlock()

	log.Printf("goose started: pid=%d args=%v", cmd.Process.Pid, args)

	// Read output in a goroutine, feeding both stdout and the in-memory buffer.
	lastActivity := time.Now()
	var lastActivityMu sync.Mutex

	doneCh := make(chan struct{})
	go func() {
		defer close(doneCh)
		buf := make([]byte, 4096)
		for {
			n, err := pr.Read(buf)
			if n > 0 {
				os.Stdout.Write(buf[:n])

				r.mu.Lock()
				r.output = append(r.output, buf[:n]...)
				if len(r.output) > maxOutputBytes {
					r.output = r.output[len(r.output)-maxOutputBytes:]
				}
				r.mu.Unlock()

				lastActivityMu.Lock()
				lastActivity = time.Now()
				lastActivityMu.Unlock()
			}
			if err != nil {
				return
			}
		}
	}()

	// Inactivity watchdog.
	sessionCtx, sessionCancel := context.WithCancel(ctx)
	defer sessionCancel()

	watchdogDone := make(chan struct{})
	go func() {
		defer close(watchdogDone)
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-sessionCtx.Done():
				return
			case <-ticker.C:
				lastActivityMu.Lock()
				elapsed := time.Since(lastActivity)
				lastActivityMu.Unlock()
				if elapsed >= inactivityTimeout {
					log.Printf("inactivity timeout (%s) reached, killing goose pid=%d", inactivityTimeout, cmd.Process.Pid)
					r.mu.Lock()
					r.output = append(r.output, []byte(fmt.Sprintf("\n--- killed: inactivity timeout (%s) ---\n", inactivityTimeout))...)
					r.mu.Unlock()
					cmd.Process.Kill()
					return
				}
			}
		}
	}()

	err := cmd.Wait()
	pw.Close()
	<-doneCh
	sessionCancel()
	<-watchdogDone

	exitCode := cmd.ProcessState.ExitCode()
	log.Printf("goose exited: pid=%d exit_code=%d", cmd.Process.Pid, exitCode)
	return exitCode, err
}

// runGoose spawns the goose process, captures output, and manages the
// inactivity watchdog. It runs in a background goroutine.
//
// When DEEP_PLAN_RECIPE is set, it runs the deep-plan session first, parses
// the output for a pipeline, then executes each step sequentially.
func (r *runner) runGoose(ctx context.Context, cancel context.CancelFunc, body RunRequest, inactivityTimeout time.Duration) {
	defer cancel()

	deepPlanRecipe := os.Getenv("DEEP_PLAN_RECIPE")

	// Determine initial session args.
	var args []string
	if deepPlanRecipe != "" {
		// Autonomous mode: use deep-plan recipe from disk.
		args = buildGooseCmdFromFile(deepPlanRecipe, body.Task, "")
	} else {
		args = buildGooseCmd(body)
	}

	// Run the initial session.
	exitCode, err := r.runSession(ctx, args, inactivityTimeout)

	// If not in autonomous mode or the session failed, finalize and return.
	if deepPlanRecipe == "" || err != nil {
		r.mu.Lock()
		r.exitCode = &exitCode
		if err != nil {
			r.state = StateFailed
		} else {
			r.state = StateDone
		}
		finalState := r.state
		r.mu.Unlock()
		log.Printf("goose session finished: exit_code=%d state=%s", exitCode, finalState)
		return
	}

	// Autonomous mode: parse the plan from deep-plan output.
	r.mu.RLock()
	outputSnapshot := string(r.output)
	r.mu.RUnlock()

	steps, parseErr := parsePlanFromOutput(outputSnapshot)
	if parseErr != nil {
		log.Printf("failed to parse plan from output: %v", parseErr)
		r.mu.Lock()
		r.exitCode = &exitCode
		r.state = StateDone
		r.mu.Unlock()
		return
	}

	if len(steps) == 0 {
		// No pipeline produced — single session mode, complete normally.
		log.Printf("deep-plan produced no pipeline, completing as single session")
		r.mu.Lock()
		r.exitCode = &exitCode
		r.state = StateDone
		r.mu.Unlock()
		return
	}

	// Build plan steps and expose via status.
	recipesDir := os.Getenv("RECIPES_DIR")
	if recipesDir == "" {
		log.Printf("RECIPES_DIR not set, cannot execute pipeline steps")
		r.mu.Lock()
		r.exitCode = &exitCode
		r.state = StateFailed
		r.mu.Unlock()
		return
	}
	planSteps := make([]PlanStep, len(steps))
	for i, s := range steps {
		planSteps[i] = PlanStep{
			Agent:       s.Agent,
			Description: s.Task,
			Status:      "pending",
		}
	}

	r.mu.Lock()
	r.plan = planSteps
	r.currentStep = 0
	r.mu.Unlock()

	log.Printf("deep-plan produced %d pipeline steps, executing sequentially", len(steps))

	// Execute each step sequentially, passing upstream output as context.
	var lastExitCode int
	var lastErr error
	var prevStepOutput string
	for i, step := range steps {
		// Check context cancellation.
		if ctx.Err() != nil {
			r.mu.Lock()
			r.plan[i].Status = "skipped"
			r.mu.Unlock()
			continue
		}

		// Evaluate condition.
		if i > 0 && step.Condition == "on success" && lastErr != nil {
			log.Printf("skipping step %d (%s): previous step failed", i, step.Agent)
			r.mu.Lock()
			r.plan[i].Status = "skipped"
			r.mu.Unlock()
			continue
		}

		// Load recipe from disk.
		recipePath := filepath.Join(recipesDir, step.Agent+".yaml")
		if _, statErr := os.Stat(recipePath); statErr != nil {
			log.Printf("recipe not found for step %d (%s): %v", i, step.Agent, statErr)
			r.mu.Lock()
			r.plan[i].Status = "failed"
			r.mu.Unlock()
			lastErr = statErr
			continue
		}

		// Update status to running.
		r.mu.Lock()
		r.plan[i].Status = "running"
		r.currentStep = i
		r.mu.Unlock()

		// Add separator in output.
		separator := fmt.Sprintf("\n--- pipeline step %d: %s ---\n", i, step.Agent)
		r.mu.Lock()
		r.output = append(r.output, []byte(separator)...)
		outputBefore := len(r.output)
		r.mu.Unlock()

		// Build task with upstream context from the previous step.
		task := step.Task
		if prevStepOutput != "" {
			task = fmt.Sprintf("## Upstream Output (from previous pipeline step)\n%s\n\n## Your Task\n%s", prevStepOutput, step.Task)
		}

		stepArgs := buildGooseCmdFromFile(recipePath, task, "")
		lastExitCode, lastErr = r.runSession(ctx, stepArgs, inactivityTimeout)

		// Capture this step's output for downstream context.
		r.mu.RLock()
		if outputBefore < len(r.output) {
			prevStepOutput = string(r.output[outputBefore:])
			// Limit context size to avoid overwhelming downstream steps.
			const maxContextBytes = 8000
			if len(prevStepOutput) > maxContextBytes {
				prevStepOutput = prevStepOutput[len(prevStepOutput)-maxContextBytes:]
			}
		}
		r.mu.RUnlock()

		// Update status based on result.
		r.mu.Lock()
		if lastErr != nil {
			r.plan[i].Status = "failed"
		} else {
			r.plan[i].Status = "completed"
		}
		r.mu.Unlock()

		log.Printf("pipeline step %d (%s) finished: exit_code=%d", i, step.Agent, lastExitCode)
	}

	// Finalize state.
	r.mu.Lock()
	r.exitCode = &lastExitCode
	// Check if any step failed.
	allSucceeded := true
	for _, ps := range r.plan {
		if ps.Status == "failed" {
			allSucceeded = false
			break
		}
	}
	if allSucceeded {
		r.state = StateDone
	} else {
		r.state = StateFailed
	}
	finalState := r.state
	r.mu.Unlock()

	log.Printf("pipeline finished: state=%s", finalState)
}

func main() {
	port := os.Getenv("RUNNER_PORT")
	if port == "" {
		port = defaultPort
	}

	r := newRunner()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", r.handleHealth)
	mux.HandleFunc("GET /status", r.handleStatus)
	mux.HandleFunc("GET /output", r.handleOutput)
	mux.HandleFunc("POST /run", r.handleRun)

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// Graceful shutdown on SIGTERM/SIGINT.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		sig := <-sigCh
		log.Printf("received %s, shutting down", sig)

		// If goose is running, kill it.
		r.mu.Lock()
		if r.cancel != nil {
			r.cancel()
		}
		r.mu.Unlock()

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		srv.Shutdown(ctx)
	}()

	log.Printf("agent-runner listening on :%s", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server error: %v", err)
	}
}

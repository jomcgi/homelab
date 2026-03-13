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
	Recipe            string `json:"recipe,omitempty"`
	Model             string `json:"model,omitempty"`
	InactivityTimeout int    `json:"inactivity_timeout,omitempty"` // seconds
}

// StatusResponse is returned by GET /status.
type StatusResponse struct {
	State     State      `json:"state"`
	PID       int        `json:"pid,omitempty"`
	ExitCode  *int       `json:"exit_code,omitempty"`
	StartedAt *time.Time `json:"started_at,omitempty"`
}

// runner holds all mutable state for the running goose process.
type runner struct {
	mu        sync.RWMutex
	state     State
	pid       int
	exitCode  *int
	startedAt *time.Time
	output    []byte
	cancel    context.CancelFunc
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
		State:     r.state,
		PID:       r.pid,
		ExitCode:  r.exitCode,
		StartedAt: r.startedAt,
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

// buildGooseCmd constructs the goose command arguments.
// When a recipe is provided, it writes it to a temp file and passes the task
// via --params so goose's MiniJinja engine handles template substitution.
// The caller must call the returned cleanup function when done.
func buildGooseCmd(body RunRequest) ([]string, func()) {
	var args []string
	var cleanup func()

	if body.Recipe != "" {
		f, err := os.CreateTemp("", "goose-recipe-*.yaml")
		if err != nil {
			log.Printf("failed to create temp recipe file: %v", err)
			args = []string{"goose", "run", "--text", body.Task}
		} else {
			f.WriteString(body.Recipe)
			f.Close()
			cleanup = func() { os.Remove(f.Name()) }
			args = []string{
				"goose", "run",
				"--recipe", f.Name(),
				"--params", "task_description=" + body.Task,
				"--no-profile",
			}
		}
	} else {
		args = []string{"goose", "run", "--text", body.Task}
	}

	if body.Model != "" {
		args = append(args, "--model", body.Model)
	}

	return args, cleanup
}

// runGoose spawns the goose process, captures output, and manages the
// inactivity watchdog. It runs in a background goroutine.
func (r *runner) runGoose(ctx context.Context, cancel context.CancelFunc, body RunRequest, inactivityTimeout time.Duration) {
	defer cancel()

	args, cleanup := buildGooseCmd(body)
	if cleanup != nil {
		defer cleanup()
	}
	cmd := exec.CommandContext(ctx, args[0], args[1:]...)
	cmd.Dir = workDir

	// Set up output capture: goose stdout+stderr -> pipe -> tee to os.Stdout + memory buffer.
	pr, pw := io.Pipe()
	cmd.Stdout = pw
	cmd.Stderr = pw

	if err := cmd.Start(); err != nil {
		log.Printf("failed to start goose: %v", err)
		r.mu.Lock()
		r.state = StateFailed
		code := -1
		r.exitCode = &code
		r.output = []byte(fmt.Sprintf("failed to start goose: %v\n", err))
		r.mu.Unlock()
		pw.Close()
		return
	}

	r.mu.Lock()
	r.pid = cmd.Process.Pid
	r.mu.Unlock()

	log.Printf("goose started: pid=%d args=%v", cmd.Process.Pid, args)

	// Read output in a goroutine, feeding both stdout and the in-memory buffer.
	// Track last activity time for the inactivity watchdog.
	lastActivity := time.Now()
	var lastActivityMu sync.Mutex

	doneCh := make(chan struct{})
	go func() {
		defer close(doneCh)
		buf := make([]byte, 4096)
		for {
			n, err := pr.Read(buf)
			if n > 0 {
				// Write to stdout for pod logs.
				os.Stdout.Write(buf[:n])

				// Append to in-memory buffer, capping at maxOutputBytes.
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

	// Inactivity watchdog: periodically check if goose has gone quiet.
	watchdogDone := make(chan struct{})
	go func() {
		defer close(watchdogDone)
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
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

	// Wait for goose to exit.
	err := cmd.Wait()
	pw.Close()
	<-doneCh
	cancel() // Stop watchdog.
	<-watchdogDone

	r.mu.Lock()
	code := cmd.ProcessState.ExitCode()
	r.exitCode = &code
	if err != nil {
		r.state = StateFailed
	} else {
		r.state = StateDone
	}
	finalState := r.state
	r.mu.Unlock()

	log.Printf("goose exited: pid=%d exit_code=%d state=%s", cmd.Process.Pid, code, finalState)
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

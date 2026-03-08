# Agent Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a long-running Go service that wraps the existing agent-run CLI logic in a REST API backed by NATS JetStream (queue) and NATS KV (state), deployable to the homelab cluster via Helm + ArgoCD.

**Architecture:** Single Go binary with three subsystems — HTTP API server, NATS JetStream pull consumer, and NATS client (JetStream + KV). The HTTP API accepts job submissions and queries, the consumer executes jobs serially by creating SandboxClaims and exec-ing Goose in sandbox pods (ported from `tools/agent-run/main.go`).

**Tech Stack:** Go 1.24+, `github.com/nats-io/nats.go` (JetStream + KV), `github.com/oklog/ulid/v2` (sortable IDs), `k8s.io/client-go` (dynamic + typed clients), `net/http` (stdlib router — Go 1.22+ method routing), Bazel + `go_image` macro, Helm chart.

**Key reference files:**

- Existing CLI to port: `tools/agent-run/main.go`
- HTTP server pattern: `services/grimoire/api/main.go`
- Helm chart pattern: `charts/stargazer/` (simple single-service chart)
- Overlay pattern: `overlays/prod/goose-sandboxes/`
- BUILD pattern: `tools/agent-run/BUILD` (Go binary), `services/grimoire/api/BUILD` (go_image)
- go_image macro: `tools/oci/go_image.bzl`

---

### Task 1: Add Go dependencies (NATS + ULID)

**Files:**

- Modify: `go.mod` (root)
- Modify: `go.sum` (root)
- Modify: `MODULE.bazel` (if gazelle needs new entries)

**Step 1: Add NATS and ULID to go.mod**

```bash
cd /tmp/claude-worktrees/agent-orchestrator
go get github.com/nats-io/nats.go@latest
go get github.com/oklog/ulid/v2@latest
```

**Step 2: Run gazelle to update BUILD files**

```bash
bazel run gazelle
```

**Step 3: Verify the build still works**

```bash
bazel build //tools/agent-run
```

Expected: BUILD SUCCESS

**Step 4: Commit**

```bash
git add go.mod go.sum MODULE.bazel
git commit -m "build: add nats.go and ulid dependencies for agent-orchestrator"
```

---

### Task 2: Create data model and job store

**Files:**

- Create: `services/agent-orchestrator/model.go`
- Create: `services/agent-orchestrator/store.go`
- Create: `services/agent-orchestrator/store_test.go`

**Step 1: Write the data model**

Create `services/agent-orchestrator/model.go`:

```go
package main

import "time"

type JobStatus string

const (
	JobPending   JobStatus = "PENDING"
	JobRunning   JobStatus = "RUNNING"
	JobSucceeded JobStatus = "SUCCEEDED"
	JobFailed    JobStatus = "FAILED"
	JobCancelled JobStatus = "CANCELLED"
)

type JobRecord struct {
	ID         string    `json:"id"`
	Task       string    `json:"task"`
	Status     JobStatus `json:"status"`
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
	MaxRetries int       `json:"max_retries"`
	Source     string    `json:"source"`

	// Reserved for webhook/DLQ integration.
	GithubIssue    int    `json:"github_issue,omitempty"`
	DebugMode      bool   `json:"debug_mode,omitempty"`
	FailureSummary string `json:"failure_summary,omitempty"`

	Attempts []Attempt `json:"attempts"`
}

type Attempt struct {
	Number           int        `json:"number"`
	SandboxClaimName string     `json:"sandbox_claim_name"`
	ExitCode         *int       `json:"exit_code,omitempty"`
	Output           string     `json:"output"`
	StartedAt        time.Time  `json:"started_at"`
	FinishedAt       *time.Time `json:"finished_at,omitempty"`
}

type SubmitRequest struct {
	Task       string `json:"task"`
	MaxRetries *int   `json:"max_retries,omitempty"`
	Source     string `json:"source,omitempty"`
}

type SubmitResponse struct {
	ID        string    `json:"id"`
	Status    JobStatus `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}

type ListResponse struct {
	Jobs  []JobRecord `json:"jobs"`
	Total int         `json:"total"`
}

type OutputResponse struct {
	Attempt   int    `json:"attempt"`
	ExitCode  *int   `json:"exit_code,omitempty"`
	Output    string `json:"output"`
	Truncated bool   `json:"truncated"`
}
```

**Step 2: Write the store interface and NATS KV implementation**

Create `services/agent-orchestrator/store.go`:

```go
package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

const kvBucket = "job-records"

type JobStore struct {
	kv jetstream.KeyValue
}

func NewJobStore(kv jetstream.KeyValue) *JobStore {
	return &JobStore{kv: kv}
}

func (s *JobStore) Put(job *JobRecord) error {
	job.UpdatedAt = time.Now().UTC()
	data, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("marshaling job: %w", err)
	}
	_, err = s.kv.Put(nil, job.ID, data)
	return err
}

func (s *JobStore) Get(id string) (*JobRecord, error) {
	entry, err := s.kv.Get(nil, id)
	if err != nil {
		return nil, err
	}
	var job JobRecord
	if err := json.Unmarshal(entry.Value(), &job); err != nil {
		return nil, fmt.Errorf("unmarshaling job: %w", err)
	}
	return &job, nil
}

func (s *JobStore) List(statusFilter []string, limit, offset int) ([]JobRecord, int, error) {
	keys, err := s.kv.Keys(nil)
	if err != nil {
		if err == jetstream.ErrNoKeysFound {
			return nil, 0, nil
		}
		return nil, 0, err
	}

	// ULIDs are lexicographically sorted by time, so sort keys descending
	// for newest-first ordering.
	sort.Sort(sort.Reverse(sort.StringSlice(keys)))

	filterSet := make(map[string]bool)
	for _, s := range statusFilter {
		filterSet[strings.ToUpper(s)] = true
	}

	var all []JobRecord
	for _, key := range keys {
		entry, err := s.kv.Get(nil, key)
		if err != nil {
			continue
		}
		var job JobRecord
		if err := json.Unmarshal(entry.Value(), &job); err != nil {
			continue
		}
		if len(filterSet) > 0 && !filterSet[string(job.Status)] {
			continue
		}
		all = append(all, job)
	}

	total := len(all)
	if offset >= total {
		return nil, total, nil
	}
	end := offset + limit
	if end > total {
		end = total
	}
	return all[offset:end], total, nil
}
```

**Step 3: Write failing tests for the store**

Create `services/agent-orchestrator/store_test.go`:

```go
package main

import (
	"context"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// startTestNATS starts an embedded NATS server for testing.
// Tests that call this require a running nats-server binary on PATH,
// or will be skipped.
func setupTestKV(t *testing.T) jetstream.KeyValue {
	t.Helper()

	// Connect to test NATS (started by test infrastructure or skipped).
	url := nats.DefaultURL
	nc, err := nats.Connect(url, nats.NoReconnect())
	if err != nil {
		t.Skipf("NATS not available at %s: %v", url, err)
	}
	t.Cleanup(func() { nc.Close() })

	js, err := jetstream.New(nc)
	if err != nil {
		t.Fatalf("creating JetStream context: %v", err)
	}

	bucket := "test-jobs-" + time.Now().Format("20060102150405")
	kv, err := js.CreateKeyValue(context.Background(), jetstream.KeyValueConfig{
		Bucket: bucket,
		TTL:    5 * time.Minute,
	})
	if err != nil {
		t.Fatalf("creating KV bucket: %v", err)
	}
	t.Cleanup(func() {
		js.DeleteKeyValue(context.Background(), bucket)
	})

	return kv
}

func TestJobStore_PutAndGet(t *testing.T) {
	kv := setupTestKV(t)
	store := NewJobStore(kv)

	job := &JobRecord{
		ID:         "01ABC",
		Task:       "fix the bug",
		Status:     JobPending,
		CreatedAt:  time.Now().UTC(),
		MaxRetries: 2,
		Source:     "api",
	}

	if err := store.Put(job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := store.Get("01ABC")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}

	if got.Task != "fix the bug" {
		t.Errorf("Task = %q, want %q", got.Task, "fix the bug")
	}
	if got.Status != JobPending {
		t.Errorf("Status = %q, want %q", got.Status, JobPending)
	}
}

func TestJobStore_List_WithStatusFilter(t *testing.T) {
	kv := setupTestKV(t)
	store := NewJobStore(kv)

	for i, status := range []JobStatus{JobPending, JobRunning, JobSucceeded} {
		job := &JobRecord{
			ID:        fmt.Sprintf("01%03d", i),
			Task:      fmt.Sprintf("task %d", i),
			Status:    status,
			CreatedAt: time.Now().UTC(),
		}
		if err := store.Put(job); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	jobs, total, err := store.List([]string{"PENDING", "RUNNING"}, 20, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}

	if total != 2 {
		t.Errorf("total = %d, want 2", total)
	}
	if len(jobs) != 2 {
		t.Errorf("len(jobs) = %d, want 2", len(jobs))
	}
}
```

Note: These tests require a running NATS server and will be skipped in `bazel test` unless a NATS server is available. For CI, they'll be tagged appropriately. The `fmt` import in the test file is needed for `fmt.Sprintf`.

**Step 4: Create BUILD file**

Create `services/agent-orchestrator/BUILD`:

```starlark
load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "agent-orchestrator_lib",
    srcs = [
        "main.go",
        "model.go",
        "store.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/agent-orchestrator",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@com_github_oklog_ulid_v2//:ulid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//kubernetes/scheme",
        "@io_k8s_client_go//rest",
        "@io_k8s_client_go//tools/remotecommand",
        "@io_k8s_client_go//util/exec",
    ],
)

go_binary(
    name = "agent-orchestrator",
    embed = [":agent-orchestrator_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "agent-orchestrator_test",
    srcs = [
        "api_test.go",
        "store_test.go",
    ],
    embed = [":agent-orchestrator_lib"],
    tags = ["manual"],  # Requires running NATS server
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
    ],
)

go_image(
    name = "image",
    binary = ":agent-orchestrator",
    repository = "ghcr.io/jomcgi/homelab/services/agent-orchestrator",
)
```

Note: `main.go` doesn't exist yet — create a minimal placeholder so the build doesn't fail:

Create `services/agent-orchestrator/main.go`:

```go
package main

func main() {}
```

**Step 5: Run gazelle and verify build**

```bash
bazel run gazelle
bazel build //services/agent-orchestrator
```

Expected: BUILD SUCCESS. Gazelle may adjust deps in the BUILD file — that's fine.

**Step 6: Commit**

```bash
git add services/agent-orchestrator/
git commit -m "feat(agent-orchestrator): add data model and NATS KV job store"
```

---

### Task 3: Implement HTTP API handlers

**Files:**

- Create: `services/agent-orchestrator/api.go`
- Create: `services/agent-orchestrator/api_test.go`
- Modify: `services/agent-orchestrator/main.go`
- Modify: `services/agent-orchestrator/BUILD` (add api.go to srcs)

**Step 1: Write API handler tests**

Create `services/agent-orchestrator/api_test.go`:

```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// mockStore is an in-memory store for unit tests (no NATS needed).
type mockStore struct {
	jobs map[string]*JobRecord
}

func newMockStore() *mockStore {
	return &mockStore{jobs: make(map[string]*JobRecord)}
}

func (m *mockStore) Put(job *JobRecord) error {
	m.jobs[job.ID] = job
	return nil
}

func (m *mockStore) Get(id string) (*JobRecord, error) {
	job, ok := m.jobs[id]
	if !ok {
		return nil, jetstream.ErrKeyNotFound
	}
	return job, nil
}

// For unit tests, extract a Store interface so we can mock.
// This means refactoring JobStore to implement an interface.
```

Actually, let me restructure. For testability without NATS, we should define a `Store` interface:

**Step 1: Refactor store.go to use an interface**

Add to the top of `services/agent-orchestrator/store.go`, before the `JobStore` struct:

```go
// Store is the interface for job persistence.
type Store interface {
	Put(job *JobRecord) error
	Get(id string) (*JobRecord, error)
	List(statusFilter []string, limit, offset int) ([]JobRecord, int, error)
}
```

`JobStore` already satisfies this interface.

**Step 2: Write the API handler**

Create `services/agent-orchestrator/api.go`:

```go
package main

import (
	"crypto/rand"
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/nats-io/nats.go/jetstream"
	"github.com/oklog/ulid/v2"
)

const defaultMaxRetries = 2

type API struct {
	store  Store
	stream jetstream.Stream
	logger *slog.Logger
}

func NewAPI(store Store, stream jetstream.Stream, logger *slog.Logger) *API {
	return &API{store: store, stream: stream, logger: logger}
}

func (a *API) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /jobs", a.handleSubmit)
	mux.HandleFunc("GET /jobs", a.handleList)
	mux.HandleFunc("GET /jobs/{id}", a.handleGet)
	mux.HandleFunc("POST /jobs/{id}/cancel", a.handleCancel)
	mux.HandleFunc("GET /jobs/{id}/output", a.handleOutput)
	mux.HandleFunc("GET /health", a.handleHealth)
}

func (a *API) handleSubmit(w http.ResponseWriter, r *http.Request) {
	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}
	if req.Task == "" {
		http.Error(w, `{"error":"task is required"}`, http.StatusBadRequest)
		return
	}

	maxRetries := defaultMaxRetries
	if req.MaxRetries != nil {
		maxRetries = *req.MaxRetries
	}
	source := req.Source
	if source == "" {
		source = "api"
	}

	now := time.Now().UTC()
	id := ulid.MustNew(ulid.Timestamp(now), rand.Reader)

	job := &JobRecord{
		ID:         id.String(),
		Task:       req.Task,
		Status:     JobPending,
		CreatedAt:  now,
		UpdatedAt:  now,
		MaxRetries: maxRetries,
		Source:     source,
	}

	if err := a.store.Put(job); err != nil {
		a.logger.Error("storing job", "error", err)
		http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
		return
	}

	// Publish job ID to JetStream for consumer pickup.
	if a.stream != nil {
		js := a.stream
		_ = js // Stream publish happens via the JetStream context, not Stream directly.
		// We need the JetStream context to publish. Refactor: pass js context instead.
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(SubmitResponse{
		ID:        job.ID,
		Status:    job.Status,
		CreatedAt: job.CreatedAt,
	})
}

func (a *API) handleList(w http.ResponseWriter, r *http.Request) {
	var statusFilter []string
	if s := r.URL.Query().Get("status"); s != "" {
		statusFilter = strings.Split(s, ",")
	}

	limit := 20
	if l := r.URL.Query().Get("limit"); l != "" {
		if v, err := strconv.Atoi(l); err == nil && v > 0 && v <= 100 {
			limit = v
		}
	}

	offset := 0
	if o := r.URL.Query().Get("offset"); o != "" {
		if v, err := strconv.Atoi(o); err == nil && v >= 0 {
			offset = v
		}
	}

	jobs, total, err := a.store.List(statusFilter, limit, offset)
	if err != nil {
		a.logger.Error("listing jobs", "error", err)
		http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
		return
	}
	if jobs == nil {
		jobs = []JobRecord{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(ListResponse{Jobs: jobs, Total: total})
}

func (a *API) handleGet(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(id)
	if err != nil {
		http.Error(w, `{"error":"job not found"}`, http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(job)
}

func (a *API) handleCancel(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(id)
	if err != nil {
		http.Error(w, `{"error":"job not found"}`, http.StatusNotFound)
		return
	}

	if job.Status != JobPending && job.Status != JobRunning {
		http.Error(w, `{"error":"job cannot be cancelled in current state"}`, http.StatusConflict)
		return
	}

	job.Status = JobCancelled
	if err := a.store.Put(job); err != nil {
		a.logger.Error("cancelling job", "error", err)
		http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(job)
}

func (a *API) handleOutput(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(id)
	if err != nil {
		http.Error(w, `{"error":"job not found"}`, http.StatusNotFound)
		return
	}

	if len(job.Attempts) == 0 {
		http.Error(w, `{"error":"no attempts yet"}`, http.StatusNotFound)
		return
	}

	latest := job.Attempts[len(job.Attempts)-1]
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(OutputResponse{
		Attempt:  latest.Number,
		ExitCode: latest.ExitCode,
		Output:   latest.Output,
	})
}

func (a *API) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
}
```

Note: The `handleSubmit` function has a TODO for JetStream publish — this gets wired up properly in Task 5 (main.go) where we have the full JetStream context available. For now, the API struct will accept a publish function instead of the stream directly. We'll refactor this in Task 5.

**Step 3: Write API tests (no NATS required)**

Create `services/agent-orchestrator/api_test.go`:

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// memStore is an in-memory Store for unit tests.
type memStore struct {
	jobs map[string]*JobRecord
}

func newMemStore() *memStore {
	return &memStore{jobs: make(map[string]*JobRecord)}
}

func (m *memStore) Put(job *JobRecord) error {
	m.jobs[job.ID] = job
	return nil
}

func (m *memStore) Get(id string) (*JobRecord, error) {
	job, ok := m.jobs[id]
	if !ok {
		return nil, jetstream.ErrKeyNotFound
	}
	return job, nil
}

func (m *memStore) List(statusFilter []string, limit, offset int) ([]JobRecord, int, error) {
	filterSet := make(map[string]bool)
	for _, s := range statusFilter {
		filterSet[strings.ToUpper(s)] = true
	}

	var all []JobRecord
	for _, job := range m.jobs {
		if len(filterSet) > 0 && !filterSet[string(job.Status)] {
			continue
		}
		all = append(all, *job)
	}
	sort.Slice(all, func(i, j int) bool { return all[i].ID > all[j].ID })

	total := len(all)
	if offset >= total {
		return nil, total, nil
	}
	end := offset + limit
	if end > total {
		end = total
	}
	return all[offset:end], total, nil
}

func TestHandleSubmit(t *testing.T) {
	store := newMemStore()
	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	body := `{"task":"fix the flaky test"}`
	req := httptest.NewRequest("POST", "/jobs", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusAccepted)
	}

	var resp SubmitResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.ID == "" {
		t.Error("expected non-empty ID")
	}
	if resp.Status != JobPending {
		t.Errorf("status = %q, want PENDING", resp.Status)
	}
}

func TestHandleSubmit_MissingTask(t *testing.T) {
	store := newMemStore()
	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("POST", "/jobs", bytes.NewBufferString(`{}`))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
}

func TestHandleGet(t *testing.T) {
	store := newMemStore()
	store.Put(&JobRecord{ID: "01TEST", Task: "do stuff", Status: JobRunning})

	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/jobs/01TEST", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var job JobRecord
	json.NewDecoder(w.Body).Decode(&job)
	if job.Task != "do stuff" {
		t.Errorf("task = %q, want %q", job.Task, "do stuff")
	}
}

func TestHandleGet_NotFound(t *testing.T) {
	store := newMemStore()
	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/jobs/NONEXISTENT", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusNotFound)
	}
}

func TestHandleList_StatusFilter(t *testing.T) {
	store := newMemStore()
	store.Put(&JobRecord{ID: "01A", Status: JobPending, Task: "a"})
	store.Put(&JobRecord{ID: "01B", Status: JobRunning, Task: "b"})
	store.Put(&JobRecord{ID: "01C", Status: JobSucceeded, Task: "c"})

	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/jobs?status=PENDING,RUNNING", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	var resp ListResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Total != 2 {
		t.Errorf("total = %d, want 2", resp.Total)
	}
}

func TestHandleCancel(t *testing.T) {
	store := newMemStore()
	store.Put(&JobRecord{ID: "01CANCEL", Status: JobPending, Task: "cancel me"})

	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("POST", "/jobs/01CANCEL/cancel", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusOK)
	}

	got, _ := store.Get("01CANCEL")
	if got.Status != JobCancelled {
		t.Errorf("status = %q, want CANCELLED", got.Status)
	}
}

func TestHandleCancel_AlreadySucceeded(t *testing.T) {
	store := newMemStore()
	store.Put(&JobRecord{ID: "01DONE", Status: JobSucceeded, Task: "done"})

	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("POST", "/jobs/01DONE/cancel", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusConflict {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusConflict)
	}
}

func TestHandleOutput(t *testing.T) {
	exitCode := 0
	store := newMemStore()
	store.Put(&JobRecord{
		ID: "01OUT", Task: "run it", Status: JobSucceeded,
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: "hello world"},
		},
	})

	api := NewAPI(store, nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/jobs/01OUT/output", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	var resp OutputResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Output != "hello world" {
		t.Errorf("output = %q, want %q", resp.Output, "hello world")
	}
}

func TestHandleHealth(t *testing.T) {
	api := NewAPI(newMemStore(), nil, slog.Default())
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusOK)
	}
}
```

Note: Tests use `slog.Default()` which requires `"log/slog"` import. The `fmt` import may be needed in some tests. The test file imports `jetstream` for `ErrKeyNotFound`. Add missing imports during implementation.

**Step 4: Update BUILD file srcs**

Add `"api.go"` to the `srcs` list in `go_library` and `"api_test.go"` to the test srcs. Run gazelle to fix deps:

```bash
bazel run gazelle
```

**Step 5: Verify tests pass**

```bash
bazel test //services/agent-orchestrator:agent-orchestrator_test
```

Note: The API tests use `memStore` (no NATS), so they should pass without the `manual` tag. We may need to split test targets — one for unit tests (no tag) and one for integration tests (`manual` tag). Adjust the BUILD file accordingly.

Expected: All API tests PASS.

**Step 6: Commit**

```bash
git add services/agent-orchestrator/
git commit -m "feat(agent-orchestrator): add REST API handlers with tests"
```

---

### Task 4: Port sandbox lifecycle from agent-run CLI

**Files:**

- Create: `services/agent-orchestrator/sandbox.go`
- Modify: `services/agent-orchestrator/BUILD` (add to srcs)

This ports the core sandbox logic from `tools/agent-run/main.go` (lines 97-317) into a reusable struct that the consumer will call. The key differences from the CLI:

- Uses in-cluster config (`rest.InClusterConfig()`) instead of kubeconfig
- Captures output to a buffer instead of streaming to stdout
- Returns structured results instead of printing

**Step 1: Create the sandbox executor**

Create `services/agent-orchestrator/sandbox.go`:

```go
package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
	executil "k8s.io/client-go/util/exec"
)

var sandboxClaimGVR = schema.GroupVersionResource{
	Group:    "extensions.agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxclaims",
}

var sandboxGVR = schema.GroupVersionResource{
	Group:    "agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxes",
}

// SandboxExecutor manages the lifecycle of sandbox pods for running Goose tasks.
type SandboxExecutor struct {
	dynClient dynamic.Interface
	clientset kubernetes.Interface
	config    *rest.Config
	namespace string
	template  string
	logger    *slog.Logger
}

// ExecResult holds the outcome of a sandbox execution.
type ExecResult struct {
	ClaimName string
	ExitCode  int
	Output    string
}

func NewSandboxExecutor(config *rest.Config, namespace, template string, logger *slog.Logger) (*SandboxExecutor, error) {
	dynClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("creating dynamic client: %w", err)
	}
	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("creating clientset: %w", err)
	}
	return &SandboxExecutor{
		dynClient: dynClient,
		clientset: clientset,
		config:    config,
		namespace: namespace,
		template:  template,
		logger:    logger,
	}, nil
}

// Run creates a SandboxClaim, waits for the pod, execs Goose with the given task,
// captures output, and cleans up. It checks cancelFn before each phase to support
// cancellation via KV status polling.
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task string, cancelFn func() bool) (*ExecResult, error) {
	result := &ExecResult{ClaimName: claimName, ExitCode: -1}

	// Phase 1: Create SandboxClaim.
	if cancelFn() {
		return result, fmt.Errorf("cancelled before claim creation")
	}
	s.logger.Info("creating SandboxClaim", "claim", claimName)
	if err := s.createClaim(ctx, claimName); err != nil {
		return result, fmt.Errorf("creating claim: %w", err)
	}
	defer s.deleteClaim(claimName)

	// Phase 2: Wait for pod.
	if cancelFn() {
		return result, fmt.Errorf("cancelled before pod allocation")
	}
	podName, err := s.waitForPod(ctx, claimName)
	if err != nil {
		return result, fmt.Errorf("waiting for pod: %w", err)
	}
	s.logger.Info("sandbox pod ready", "pod", podName)

	// Phase 3: Wait for pod running.
	if cancelFn() {
		return result, fmt.Errorf("cancelled before pod ready")
	}
	if err := s.waitPodRunning(ctx, podName); err != nil {
		return result, fmt.Errorf("waiting for pod running: %w", err)
	}

	// Phase 4: Refresh workspace.
	if cancelFn() {
		return result, fmt.Errorf("cancelled before workspace refresh")
	}
	if err := s.refreshWorkspace(ctx, podName); err != nil {
		s.logger.Warn("workspace refresh failed (continuing)", "error", err)
	}

	// Phase 5: Exec goose.
	if cancelFn() {
		return result, fmt.Errorf("cancelled before exec")
	}
	s.logger.Info("executing goose task", "pod", podName)
	exitCode, output, err := s.execGoose(ctx, podName, task)
	if err != nil {
		return result, fmt.Errorf("exec goose: %w", err)
	}

	result.ExitCode = exitCode
	result.Output = output
	return result, nil
}

func (s *SandboxExecutor) createClaim(ctx context.Context, name string) error {
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": s.namespace,
			},
			"spec": map[string]interface{}{
				"sandboxTemplateRef": map[string]interface{}{
					"name": s.template,
				},
				"lifecycle": map[string]interface{}{
					"shutdownPolicy": "Delete",
				},
			},
		},
	}
	_, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Create(ctx, claim, metav1.CreateOptions{})
	return err
}

func (s *SandboxExecutor) deleteClaim(name string) {
	s.logger.Info("cleaning up SandboxClaim", "claim", name)
	_ = s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Delete(
		context.Background(), name, metav1.DeleteOptions{})
}

func (s *SandboxExecutor) waitForPod(ctx context.Context, claimName string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

	for {
		claim, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Get(ctx, claimName, metav1.GetOptions{})
		if err != nil {
			return "", err
		}
		if status, ok := claim.Object["status"].(map[string]interface{}); ok {
			if sandbox, _ := status["sandbox"].(map[string]interface{}); sandbox != nil {
				if sandboxName, _ := sandbox["Name"].(string); sandboxName != "" {
					return s.resolvePodName(ctx, sandboxName)
				}
			}
		}
		select {
		case <-ctx.Done():
			return "", fmt.Errorf("timed out waiting for sandbox allocation")
		case <-time.After(2 * time.Second):
		}
	}
}

func (s *SandboxExecutor) resolvePodName(ctx context.Context, sandboxName string) (string, error) {
	sandbox, err := s.dynClient.Resource(sandboxGVR).Namespace(s.namespace).Get(ctx, sandboxName, metav1.GetOptions{})
	if err != nil {
		return "", fmt.Errorf("getting Sandbox %s: %w", sandboxName, err)
	}
	if podName, ok := sandbox.GetAnnotations()["agents.x-k8s.io/pod-name"]; ok && podName != "" {
		return podName, nil
	}
	return sandboxName, nil
}

func (s *SandboxExecutor) waitPodRunning(ctx context.Context, podName string) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	for {
		pod, err := s.clientset.CoreV1().Pods(s.namespace).Get(ctx, podName, metav1.GetOptions{})
		if err != nil {
			return err
		}
		if pod.Status.Phase == corev1.PodRunning {
			for _, cs := range pod.Status.ContainerStatuses {
				if cs.Name == "goose" && cs.Ready {
					return nil
				}
			}
		}
		if pod.Status.Phase == corev1.PodFailed {
			return fmt.Errorf("pod failed: %s", pod.Status.Message)
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("timed out waiting for pod to be ready")
		case <-time.After(2 * time.Second):
		}
	}
}

func (s *SandboxExecutor) refreshWorkspace(ctx context.Context, podName string) error {
	req := s.clientset.CoreV1().RESTClient().Post().
		Resource("pods").Name(podName).Namespace(s.namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: "goose",
			Command:   []string{"git", "-C", "/workspace/homelab", "pull", "--ff-only", "origin", "main"},
			Stdout:    true, Stderr: true,
		}, scheme.ParameterCodec)

	exec, err := remotecommand.NewSPDYExecutor(s.config, "POST", req.URL())
	if err != nil {
		return err
	}
	return exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: io.Discard, Stderr: io.Discard,
	})
}

func (s *SandboxExecutor) execGoose(ctx context.Context, podName, task string) (int, string, error) {
	req := s.clientset.CoreV1().RESTClient().Post().
		Resource("pods").Name(podName).Namespace(s.namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: "goose",
			Command:   []string{"goose", "run", "--text", task},
			Stdout:    true, Stderr: true,
		}, scheme.ParameterCodec)

	exec, err := remotecommand.NewSPDYExecutor(s.config, "POST", req.URL())
	if err != nil {
		return -1, "", err
	}

	var buf bytes.Buffer
	// Tee output to both buffer (for KV storage) and stdout (for pod logs).
	stdout := io.MultiWriter(&buf, logWriter{s.logger, "stdout"})
	stderr := io.MultiWriter(&buf, logWriter{s.logger, "stderr"})

	err = exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: stdout, Stderr: stderr,
	})
	if err != nil {
		if exitErr, ok := err.(executil.ExitError); ok {
			return exitErr.ExitStatus(), buf.String(), nil
		}
		return -1, buf.String(), err
	}
	return 0, buf.String(), nil
}

// logWriter adapts slog to io.Writer for streaming exec output to structured logs.
type logWriter struct {
	logger *slog.Logger
	stream string
}

func (w logWriter) Write(p []byte) (int, error) {
	w.logger.Debug("goose output", "stream", w.stream, "data", string(p))
	return len(p), nil
}
```

**Step 2: Update BUILD and run gazelle**

Add `"sandbox.go"` to the srcs list in the go_library. Then:

```bash
bazel run gazelle
bazel build //services/agent-orchestrator
```

Expected: BUILD SUCCESS

**Step 3: Commit**

```bash
git add services/agent-orchestrator/sandbox.go services/agent-orchestrator/BUILD
git commit -m "feat(agent-orchestrator): port sandbox lifecycle from agent-run CLI"
```

---

### Task 5: Implement consumer and wire up main.go

**Files:**

- Create: `services/agent-orchestrator/consumer.go`
- Modify: `services/agent-orchestrator/main.go` (full implementation)
- Modify: `services/agent-orchestrator/api.go` (refactor to accept publish function)
- Modify: `services/agent-orchestrator/BUILD`

**Step 1: Create the consumer**

Create `services/agent-orchestrator/consumer.go`:

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

const maxOutputBytes = 512 * 1024 // 512KB max output stored in KV

// Consumer pulls jobs from JetStream and executes them via SandboxExecutor.
type Consumer struct {
	cons    jetstream.Consumer
	store   Store
	sandbox *SandboxExecutor
	logger  *slog.Logger
}

func NewConsumer(cons jetstream.Consumer, store Store, sandbox *SandboxExecutor, logger *slog.Logger) *Consumer {
	return &Consumer{cons: cons, store: store, sandbox: sandbox, logger: logger}
}

// Run processes jobs until ctx is cancelled.
func (c *Consumer) Run(ctx context.Context) {
	c.logger.Info("consumer started, waiting for jobs")
	for {
		msgs, err := c.cons.Fetch(1, jetstream.FetchMaxWait(30*time.Second))
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			c.logger.Error("fetching message", "error", err)
			time.Sleep(time.Second)
			continue
		}

		for msg := range msgs.Messages() {
			c.processJob(ctx, msg)
		}

		if ctx.Err() != nil {
			return
		}
	}
}

func (c *Consumer) processJob(ctx context.Context, msg jetstream.Msg) {
	jobID := string(msg.Data())
	logger := c.logger.With("job_id", jobID)

	job, err := c.store.Get(jobID)
	if err != nil {
		logger.Error("fetching job record", "error", err)
		msg.Ack()
		return
	}

	if job.Status == JobCancelled {
		logger.Info("job already cancelled, skipping")
		msg.Ack()
		return
	}

	attemptNum := len(job.Attempts) + 1
	logger = logger.With("attempt", attemptNum)
	logger.Info("starting job execution")

	// Update status to RUNNING.
	job.Status = JobRunning
	now := time.Now().UTC()
	claimName := fmt.Sprintf("orch-%s-%d", jobID[:8], attemptNum)
	attempt := Attempt{
		Number:           attemptNum,
		SandboxClaimName: claimName,
		StartedAt:        now,
	}
	job.Attempts = append(job.Attempts, attempt)
	c.store.Put(job)

	// Build task prompt (with context from previous attempts for retries).
	task := c.buildTaskPrompt(job)

	// Check cancellation by reading KV status.
	cancelFn := func() bool {
		j, err := c.store.Get(jobID)
		if err != nil {
			return false
		}
		return j.Status == JobCancelled
	}

	// Execute in sandbox.
	result, execErr := c.sandbox.Run(ctx, claimName, task, cancelFn)

	// Update attempt result.
	finishedAt := time.Now().UTC()
	lastAttempt := &job.Attempts[len(job.Attempts)-1]
	lastAttempt.FinishedAt = &finishedAt

	if result != nil {
		lastAttempt.ExitCode = &result.ExitCode
		output := result.Output
		if len(output) > maxOutputBytes {
			output = output[:maxOutputBytes] + "\n... [truncated]"
		}
		lastAttempt.Output = output
	}

	// Re-check cancellation.
	fresh, _ := c.store.Get(jobID)
	if fresh != nil && fresh.Status == JobCancelled {
		logger.Info("job cancelled during execution")
		job.Status = JobCancelled
		c.store.Put(job)
		msg.Ack()
		return
	}

	if execErr != nil || (result != nil && result.ExitCode != 0) {
		if execErr != nil {
			logger.Error("sandbox execution failed", "error", execErr)
		} else {
			logger.Warn("goose exited with non-zero code", "exit_code", result.ExitCode)
		}

		if attemptNum <= job.MaxRetries {
			logger.Info("retrying job", "next_attempt", attemptNum+1)
			c.store.Put(job)
			msg.Nak() // Re-deliver for retry.
			return
		}

		logger.Warn("job exhausted all retries", "total_attempts", attemptNum)
		job.Status = JobFailed
	} else {
		logger.Info("job completed successfully")
		job.Status = JobSucceeded
	}

	c.store.Put(job)
	msg.Ack()
}

func (c *Consumer) buildTaskPrompt(job *JobRecord) string {
	if len(job.Attempts) <= 1 {
		return job.Task
	}

	// Include context from previous attempts.
	prev := job.Attempts[len(job.Attempts)-2]
	var exitInfo string
	if prev.ExitCode != nil {
		exitInfo = fmt.Sprintf("exit code %d", *prev.ExitCode)
	} else {
		exitInfo = "unknown error"
	}

	outputSummary := prev.Output
	if len(outputSummary) > 2000 {
		outputSummary = outputSummary[len(outputSummary)-2000:]
	}

	return fmt.Sprintf(`Previous attempt failed (%s).
Output (last 2000 chars):
%s

Original task:
%s

Try a different approach.`, exitInfo, outputSummary, job.Task)
}
```

**Step 2: Refactor API to accept a publish function**

In `services/agent-orchestrator/api.go`, change the `API` struct to hold a publish function instead of a stream:

Replace the `API` struct and `NewAPI`:

```go
type API struct {
	store   Store
	publish func(jobID string) error // publishes job ID to JetStream
	logger  *slog.Logger
}

func NewAPI(store Store, publish func(string) error, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, logger: logger}
}
```

Update `handleSubmit` to call the publish function after storing:

```go
// In handleSubmit, after store.Put(job), replace the stream TODO block with:
if a.publish != nil {
    if err := a.publish(job.ID); err != nil {
        a.logger.Error("publishing job to queue", "error", err)
        // Job is stored but not queued — it can be re-queued manually.
    }
}
```

Update test to match new signature: `NewAPI(store, nil, slog.Default())` — already matches since `publish` is a function that can be nil.

**Step 3: Implement main.go**

Replace `services/agent-orchestrator/main.go`:

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"k8s.io/client-go/rest"
)

const (
	streamName = "agent-jobs"
	subject    = "agent.jobs"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()

	// Config from environment.
	natsURL := envOr("NATS_URL", nats.DefaultURL)
	sandboxNS := envOr("SANDBOX_NAMESPACE", "goose-sandboxes")
	sandboxTemplate := envOr("SANDBOX_TEMPLATE", "goose-agent")
	maxRetries, _ := strconv.Atoi(envOr("MAX_RETRIES", "2"))
	_ = maxRetries // Used by API default
	httpPort := envOr("HTTP_PORT", "8080")

	// Connect to NATS.
	nc, err := nats.Connect(natsURL,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
	)
	if err != nil {
		logger.Error("connecting to NATS", "error", err)
		os.Exit(1)
	}
	defer nc.Close()
	logger.Info("connected to NATS", "url", natsURL)

	// Set up JetStream.
	js, err := jetstream.New(nc)
	if err != nil {
		logger.Error("creating JetStream context", "error", err)
		os.Exit(1)
	}

	// Ensure stream exists.
	stream, err := js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:      streamName,
		Subjects:  []string{subject},
		Retention: jetstream.WorkQueuePolicy,
		MaxMsgs:   1000,
	})
	if err != nil {
		logger.Error("creating stream", "error", err)
		os.Exit(1)
	}
	logger.Info("JetStream stream ready", "name", streamName)

	// Ensure KV bucket exists.
	kv, err := js.CreateOrUpdateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: kvBucket,
		TTL:    7 * 24 * time.Hour,
	})
	if err != nil {
		logger.Error("creating KV bucket", "error", err)
		os.Exit(1)
	}
	logger.Info("NATS KV bucket ready", "bucket", kvBucket)

	// Create durable pull consumer.
	cons, err := stream.CreateOrUpdateConsumer(ctx, jetstream.ConsumerConfig{
		Durable:       "orchestrator",
		AckPolicy:     jetstream.AckExplicitPolicy,
		MaxAckPending: 1,
	})
	if err != nil {
		logger.Error("creating consumer", "error", err)
		os.Exit(1)
	}

	// Set up Kubernetes client (in-cluster).
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		logger.Warn("in-cluster config unavailable, sandbox execution will fail", "error", err)
		// Allow service to start for API-only use during local dev.
		k8sConfig = nil
	}

	// Create store.
	store := NewJobStore(kv)

	// Create sandbox executor (nil if no k8s config).
	var sandbox *SandboxExecutor
	if k8sConfig != nil {
		sandbox, err = NewSandboxExecutor(k8sConfig, sandboxNS, sandboxTemplate, logger)
		if err != nil {
			logger.Error("creating sandbox executor", "error", err)
			os.Exit(1)
		}
	}

	// Publish function for the API.
	publish := func(jobID string) error {
		_, err := js.Publish(ctx, subject, []byte(jobID))
		return err
	}

	// Set up HTTP API.
	api := NewAPI(store, publish, logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	srv := &http.Server{
		Addr:              ":" + httpPort,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// Start consumer goroutine.
	if sandbox != nil {
		consumer := NewConsumer(cons, store, sandbox, logger)
		go consumer.Run(ctx)
	} else {
		logger.Warn("sandbox executor not available, consumer not started")
	}

	// Start HTTP server.
	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		srv.Shutdown(shutdownCtx)
	}()

	logger.Info("agent-orchestrator listening", "port", httpPort)
	if err := srv.ListenAndServe(); err != http.ErrServerClosed {
		logger.Error("server error", "error", err)
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
```

**Step 4: Update BUILD and run gazelle**

Add `"consumer.go"` to srcs. Then:

```bash
bazel run gazelle
bazel build //services/agent-orchestrator
```

Expected: BUILD SUCCESS

**Step 5: Commit**

```bash
git add services/agent-orchestrator/
git commit -m "feat(agent-orchestrator): add consumer, wire up main.go with NATS and HTTP server"
```

---

### Task 6: Create Helm chart

**Files:**

- Create: `charts/agent-orchestrator/Chart.yaml`
- Create: `charts/agent-orchestrator/values.yaml`
- Create: `charts/agent-orchestrator/templates/_helpers.tpl`
- Create: `charts/agent-orchestrator/templates/deployment.yaml`
- Create: `charts/agent-orchestrator/templates/service.yaml`
- Create: `charts/agent-orchestrator/templates/serviceaccount.yaml`
- Create: `charts/agent-orchestrator/templates/rbac.yaml`
- Create: `charts/agent-orchestrator/BUILD`

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: agent-orchestrator
description: Orchestrates Goose agent tasks via REST API with NATS-backed queue and state
type: application
version: 0.1.0
appVersion: "0.1.0"
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

```yaml
replicaCount: 1

image:
  repository: ghcr.io/jomcgi/homelab/services/agent-orchestrator
  tag: main
  pullPolicy: IfNotPresent

imagePullSecret:
  enabled: false
  create: true
  onepassword:
    itemPath: "vaults/k8s-homelab/items/ghcr-read-permissions"

nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations: {}

podSecurityContext:
  seccompProfile:
    type: RuntimeDefault

securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: 8080

resources:
  requests:
    cpu: 10m
    memory: 64Mi
  limits:
    cpu: 100m
    memory: 128Mi

config:
  natsUrl: "nats://nats.nats.svc.cluster.local:4222"
  sandboxNamespace: "goose-sandboxes"
  sandboxTemplate: "goose-agent"
  maxRetries: "2"
  httpPort: "8080"

rbac:
  sandboxNamespace: "goose-sandboxes"

nodeSelector: {}
tolerations: []
affinity: {}

imageUpdater:
  enabled: false
  images: []
  writeBack:
    method: ""
    repository: ""
    branch: main
    target: ""
```

**Step 3: Create templates/\_helpers.tpl**

Use the standard pattern from stargazer (copy and replace "stargazer" with "agent-orchestrator"):

```
{{/*
Expand the name of the chart.
*/}}
{{- define "agent-orchestrator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "agent-orchestrator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "agent-orchestrator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "agent-orchestrator.labels" -}}
helm.sh/chart: {{ include "agent-orchestrator.chart" . }}
{{ include "agent-orchestrator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "agent-orchestrator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent-orchestrator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "agent-orchestrator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "agent-orchestrator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
```

**Step 4: Create templates/deployment.yaml**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "agent-orchestrator.fullname" . }}
  labels:
    {{- include "agent-orchestrator.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  strategy:
    type: Recreate
  selector:
    matchLabels:
      {{- include "agent-orchestrator.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "agent-orchestrator.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ include "agent-orchestrator.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
      - name: orchestrator
        securityContext:
          {{- toYaml .Values.securityContext | nindent 10 }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: {{ .Values.config.httpPort }}
          protocol: TCP
        env:
        - name: NATS_URL
          value: {{ .Values.config.natsUrl | quote }}
        - name: SANDBOX_NAMESPACE
          value: {{ .Values.config.sandboxNamespace | quote }}
        - name: SANDBOX_TEMPLATE
          value: {{ .Values.config.sandboxTemplate | quote }}
        - name: MAX_RETRIES
          value: {{ .Values.config.maxRetries | quote }}
        - name: HTTP_PORT
          value: {{ .Values.config.httpPort | quote }}
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 5
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 3
          periodSeconds: 10
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

Note: `strategy: Recreate` — single consumer by design, no rolling update needed.

**Step 5: Create templates/service.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: { { include "agent-orchestrator.fullname" . } }
  labels: { { - include "agent-orchestrator.labels" . | nindent 4 } }
spec:
  type: { { .Values.service.type } }
  ports:
    - port: { { .Values.service.port } }
      targetPort: http
      protocol: TCP
      name: http
  selector: { { - include "agent-orchestrator.selectorLabels" . | nindent 4 } }
```

**Step 6: Create templates/serviceaccount.yaml**

```yaml
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "agent-orchestrator.serviceAccountName" . }}
  labels:
    {{- include "agent-orchestrator.labels" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
```

**Step 7: Create templates/rbac.yaml**

```yaml
{{- if .Values.serviceAccount.create -}}
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "agent-orchestrator.fullname" . }}
  labels:
    {{- include "agent-orchestrator.labels" . | nindent 4 }}
rules:
  - apiGroups: ["extensions.agents.x-k8s.io"]
    resources: ["sandboxclaims"]
    verbs: ["create", "get", "list", "watch", "delete"]
  - apiGroups: ["agents.x-k8s.io"]
    resources: ["sandboxes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "agent-orchestrator.fullname" . }}
  labels:
    {{- include "agent-orchestrator.labels" . | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ include "agent-orchestrator.fullname" . }}
subjects:
  - kind: ServiceAccount
    name: {{ include "agent-orchestrator.serviceAccountName" . }}
    namespace: {{ .Release.Namespace }}
{{- end }}
```

**Step 8: Create BUILD**

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays/prod/agent-orchestrator:__pkg__"],
)
```

**Step 9: Verify helm template renders**

```bash
helm template agent-orchestrator charts/agent-orchestrator/ -f charts/agent-orchestrator/values.yaml
```

Expected: Valid YAML output with Deployment, Service, SA, ClusterRole, ClusterRoleBinding.

**Step 10: Commit**

```bash
git add charts/agent-orchestrator/
git commit -m "feat(agent-orchestrator): add Helm chart with deployment, service, RBAC"
```

---

### Task 7: Create ArgoCD overlay

**Files:**

- Create: `overlays/prod/agent-orchestrator/application.yaml`
- Create: `overlays/prod/agent-orchestrator/kustomization.yaml`
- Create: `overlays/prod/agent-orchestrator/values.yaml`
- Create: `overlays/prod/agent-orchestrator/imageupdater.yaml`
- Create: `overlays/prod/agent-orchestrator/BUILD`
- Modify: `overlays/prod/kustomization.yaml` (add agent-orchestrator)

**Step 1: Create application.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: agent-orchestrator
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/agent-orchestrator
    targetRevision: HEAD
    helm:
      releaseName: agent-orchestrator
      valueFiles:
        - values.yaml
        - ../../overlays/prod/agent-orchestrator/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: agent-orchestrator
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**Step 2: Create kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - imageupdater.yaml
```

**Step 3: Create values.yaml (prod overrides)**

```yaml
imagePullSecret:
  enabled: true

image:
  tag: main
  repository: ghcr.io/jomcgi/homelab/services/agent-orchestrator
```

**Step 4: Create imageupdater.yaml**

```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: agent-orchestrator
  namespace: argocd
spec:
  applicationRefs:
    - images:
        - alias: agent-orchestrator
          commonUpdateSettings:
            updateStrategy: digest
            forceUpdate: false
          imageName: ghcr.io/jomcgi/homelab/services/agent-orchestrator:main
          manifestTargets:
            helm:
              name: image.repository
              tag: image.tag
      namePattern: prod-agent-orchestrator
  namespace: argocd
  writeBackConfig:
    method: git:secret:argocd/argocd-image-updater-token
    gitConfig:
      repository: https://github.com/jomcgi/homelab.git
      branch: main
      writeBackTarget: helmvalues:../../overlays/prod/agent-orchestrator/values.yaml
```

**Step 5: Create BUILD**

```starlark
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "agent-orchestrator",
    chart = "charts/agent-orchestrator",
    chart_files = "//charts/agent-orchestrator:chart",
    namespace = "agent-orchestrator",
    release_name = "agent-orchestrator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/agent-orchestrator:values.yaml",
        "values.yaml",
    ],
)
```

**Step 6: Add to prod kustomization**

In `overlays/prod/kustomization.yaml`, add `- ./agent-orchestrator` to the resources list (alphabetically).

**Step 7: Verify the overlay builds**

```bash
bazel build //overlays/prod/agent-orchestrator
```

Expected: BUILD SUCCESS

**Step 8: Commit**

```bash
git add overlays/prod/agent-orchestrator/ overlays/prod/kustomization.yaml
git commit -m "feat(agent-orchestrator): add ArgoCD overlay for prod deployment"
```

---

### Task 8: Final build verification and cleanup

**Step 1: Run full build**

```bash
bazel build //...
```

Expected: BUILD SUCCESS

**Step 2: Run format check**

```bash
format
```

Fix any formatting issues.

**Step 3: Run tests**

```bash
bazel test //services/agent-orchestrator:agent-orchestrator_test
```

For tests that require NATS, they'll be skipped in CI (tagged `manual`). The API unit tests should pass.

**Step 4: Verify helm template**

```bash
helm template agent-orchestrator charts/agent-orchestrator/ -f charts/agent-orchestrator/values.yaml -f overlays/prod/agent-orchestrator/values.yaml
```

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "style: format and fix lint issues"
```

**Step 6: Push and create PR**

```bash
git push -u origin feat/agent-orchestrator
gh pr create --title "feat: add agent-orchestrator service" --body "$(cat <<'EOF'
## Summary

Adds the agent-orchestrator service — a REST API backed by NATS JetStream + KV that wraps the existing agent-run CLI logic into a long-running, durable service.

- REST API: POST/GET /jobs, cancel, output, health
- NATS JetStream queue with max-in-flight=1 consumer
- NATS KV for job state persistence
- Retry with context inheritance (previous attempt output in prompt)
- Cancellation via KV status polling
- Ported SandboxClaim lifecycle from tools/agent-run
- Helm chart with RBAC for sandbox operations
- ArgoCD overlay for prod deployment

See ADR 007 and design doc in docs/plans/ for full details.

## Test plan

- [ ] `bazel build //services/agent-orchestrator` passes
- [ ] `bazel test //services/agent-orchestrator:agent-orchestrator_test` passes (API unit tests)
- [ ] `helm template` renders valid manifests
- [ ] Overlay builds in `bazel build //overlays/prod/agent-orchestrator`
- [ ] Full `bazel build //...` passes
- [ ] Deploy to cluster: ArgoCD syncs, pod starts, health endpoint responds
- [ ] Submit a test job via `curl -X POST .../jobs -d '{"task":"echo hello"}'`
- [ ] Verify job appears in `GET /jobs` and output in `GET /jobs/:id/output`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

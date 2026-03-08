# Cluster Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an autonomous agent framework that continuously monitors the cluster using cheap local LLM compute (llama.cpp) and escalates actionable findings to Claude via the agent-orchestrator.

**Architecture:** A single Go binary running multiple agent loops. Each agent follows a Collect → Analyze → Execute pipeline. Collectors gather structured data from cluster APIs, the analyzer sends it to llama.cpp for classification, and the escalator routes findings by severity (log / GitHub issue / orchestrator job). A NATS KV-backed findings store handles deduplication and locking.

**Tech Stack:** Go, NATS JetStream KV, llama.cpp (OpenAI-compatible API), K8s client-go, Helm, Bazel (rules_go + go_image)

---

## Phase 1: Core Framework + MVP Patrol (Tasks 1-10)

### Task 1: Scaffold service and define core types

**Files:**

- Create: `services/cluster-agents/main.go`
- Create: `services/cluster-agents/model.go`

**Step 1: Create model.go with core types**

```go
package main

import (
	"context"
	"time"
)

// Severity levels for findings.
type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

// ActionType determines escalation path.
type ActionType string

const (
	ActionLog              ActionType = "log"
	ActionGitHubIssue      ActionType = "github_issue"
	ActionOrchestratorJob  ActionType = "orchestrator_job"
)

// Finding represents a single observation from a collector.
type Finding struct {
	Fingerprint string         `json:"fingerprint"`
	Source      string         `json:"source"`
	Severity    Severity       `json:"severity"`
	Title       string         `json:"title"`
	Detail      string         `json:"detail"`
	Data        map[string]any `json:"data,omitempty"`
	Timestamp   time.Time      `json:"timestamp"`
}

// Action represents an escalation decision from the analyzer.
type Action struct {
	Type    ActionType     `json:"type"`
	Finding Finding        `json:"finding"`
	Payload map[string]any `json:"payload,omitempty"`
}

// Agent defines the interface for autonomous agent loops.
type Agent interface {
	Name() string
	Collect(ctx context.Context) ([]Finding, error)
	Analyze(ctx context.Context, findings []Finding) ([]Action, error)
	Execute(ctx context.Context, actions []Action) error
	Interval() time.Duration
}
```

**Step 2: Create minimal main.go**

```go
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	slog.Info("cluster-agents starting")
	<-ctx.Done()
	slog.Info("cluster-agents shutting down")
}
```

**Step 3: Commit**

```bash
git add services/cluster-agents/
git commit -m "feat(cluster-agents): scaffold service with core types"
```

---

### Task 2: Agent loop runner with tests

**Files:**

- Create: `services/cluster-agents/runner.go`
- Create: `services/cluster-agents/runner_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"sync"
	"testing"
	"time"
)

type fakeAgent struct {
	name     string
	interval time.Duration
	mu       sync.Mutex
	sweeps   int
	findings []Finding
	actions  []Action
}

func (a *fakeAgent) Name() string              { return a.name }
func (a *fakeAgent) Interval() time.Duration   { return a.interval }

func (a *fakeAgent) Collect(_ context.Context) ([]Finding, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.sweeps++
	return a.findings, nil
}

func (a *fakeAgent) Analyze(_ context.Context, findings []Finding) ([]Action, error) {
	return a.actions, nil
}

func (a *fakeAgent) Execute(_ context.Context, actions []Action) error {
	return nil
}

func (a *fakeAgent) getSweeps() int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.sweeps
}

func TestRunnerExecutesAgentLoop(t *testing.T) {
	agent := &fakeAgent{
		name:     "test-agent",
		interval: 50 * time.Millisecond,
	}

	r := NewRunner([]Agent{agent})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	sweeps := agent.getSweeps()
	if sweeps < 2 {
		t.Errorf("expected at least 2 sweeps, got %d", sweeps)
	}
}

func TestRunnerRunsMultipleAgents(t *testing.T) {
	a1 := &fakeAgent{name: "agent-1", interval: 50 * time.Millisecond}
	a2 := &fakeAgent{name: "agent-2", interval: 50 * time.Millisecond}

	r := NewRunner([]Agent{a1, a2})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if a1.getSweeps() < 2 {
		t.Errorf("agent-1: expected at least 2 sweeps, got %d", a1.getSweeps())
	}
	if a2.getSweeps() < 2 {
		t.Errorf("agent-2: expected at least 2 sweeps, got %d", a2.getSweeps())
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestRunner -v`
Expected: FAIL — `NewRunner` undefined

**Step 3: Write runner.go**

```go
package main

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// Runner manages the lifecycle of multiple agent loops.
type Runner struct {
	agents []Agent
}

// NewRunner creates a runner for the given agents.
func NewRunner(agents []Agent) *Runner {
	return &Runner{agents: agents}
}

// Run starts all agent loops and blocks until ctx is cancelled.
func (r *Runner) Run(ctx context.Context) {
	var wg sync.WaitGroup

	for _, agent := range r.agents {
		wg.Add(1)
		go func(a Agent) {
			defer wg.Done()
			r.runAgent(ctx, a)
		}(agent)
	}

	wg.Wait()
}

func (r *Runner) runAgent(ctx context.Context, agent Agent) {
	slog.Info("agent loop starting", "agent", agent.Name(), "interval", agent.Interval())

	// Run immediately on startup, then on ticker.
	r.sweep(ctx, agent)

	ticker := time.NewTicker(agent.Interval())
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.Info("agent loop stopping", "agent", agent.Name())
			return
		case <-ticker.C:
			r.sweep(ctx, agent)
		}
	}
}

func (r *Runner) sweep(ctx context.Context, agent Agent) {
	start := time.Now()
	logger := slog.With("agent", agent.Name())

	findings, err := agent.Collect(ctx)
	if err != nil {
		logger.Error("collect failed", "error", err)
		return
	}

	actions, err := agent.Analyze(ctx, findings)
	if err != nil {
		logger.Error("analyze failed", "error", err)
		return
	}

	if err := agent.Execute(ctx, actions); err != nil {
		logger.Error("execute failed", "error", err)
		return
	}

	logger.Info("sweep complete",
		"findings", len(findings),
		"actions", len(actions),
		"duration", time.Since(start),
	)
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestRunner -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/runner.go services/cluster-agents/runner_test.go
git commit -m "feat(cluster-agents): add agent loop runner with tests"
```

---

### Task 3: Findings store with deduplication

**Files:**

- Create: `services/cluster-agents/store.go`
- Create: `services/cluster-agents/store_test.go`

**Step 1: Write the failing tests**

```go
package main

import (
	"context"
	"testing"
	"time"
)

func TestFindingsStore_ShouldEscalate_NewFinding(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected new finding to be escalatable")
	}
}

func TestFindingsStore_ShouldEscalate_DuplicateFinding(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Hour)

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Error("expected escalated finding to be blocked")
	}
}

func TestFindingsStore_MarkResolved(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Hour)
	store.MarkResolved(ctx, "fp-1")

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected resolved finding to be escalatable again")
	}
}

func TestFindingsStore_TTLExpiry(t *testing.T) {
	store := NewMemFindingsStore()
	ctx := context.Background()

	store.MarkEscalated(ctx, "fp-1", 1*time.Millisecond)
	time.Sleep(5 * time.Millisecond)

	ok, err := store.ShouldEscalate(ctx, "fp-1")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("expected expired finding to be escalatable")
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `cd services/cluster-agents && go test -run TestFindingsStore -v`
Expected: FAIL — `NewMemFindingsStore` undefined

**Step 3: Write store.go**

```go
package main

import (
	"context"
	"sync"
	"time"
)

// FindingsStore tracks escalated findings for deduplication.
type FindingsStore interface {
	ShouldEscalate(ctx context.Context, fingerprint string) (bool, error)
	MarkEscalated(ctx context.Context, fingerprint string, ttl time.Duration) error
	MarkResolved(ctx context.Context, fingerprint string) error
}

type findingEntry struct {
	ExpiresAt time.Time
}

// MemFindingsStore is an in-memory implementation for testing and single-instance use.
type MemFindingsStore struct {
	mu      sync.Mutex
	entries map[string]findingEntry
}

func NewMemFindingsStore() *MemFindingsStore {
	return &MemFindingsStore{entries: make(map[string]findingEntry)}
}

func (s *MemFindingsStore) ShouldEscalate(_ context.Context, fingerprint string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, exists := s.entries[fingerprint]
	if !exists {
		return true, nil
	}
	if time.Now().After(entry.ExpiresAt) {
		delete(s.entries, fingerprint)
		return true, nil
	}
	return false, nil
}

func (s *MemFindingsStore) MarkEscalated(_ context.Context, fingerprint string, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.entries[fingerprint] = findingEntry{ExpiresAt: time.Now().Add(ttl)}
	return nil
}

func (s *MemFindingsStore) MarkResolved(_ context.Context, fingerprint string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.entries, fingerprint)
	return nil
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestFindingsStore -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/store.go services/cluster-agents/store_test.go
git commit -m "feat(cluster-agents): add findings store with dedup and TTL"
```

---

### Task 4: NATS KV findings store implementation

**Files:**

- Create: `services/cluster-agents/store_nats.go`

**Step 1: Write store_nats.go**

This wraps NATS KV to implement the `FindingsStore` interface. No unit test needed — the interface is tested via `MemFindingsStore`, and NATS KV is an integration concern.

```go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// NATSFindingsStore persists findings in a NATS KV bucket.
type NATSFindingsStore struct {
	kv jetstream.KeyValue
}

type natsEntry struct {
	ExpiresAt time.Time `json:"expires_at"`
}

func NewNATSFindingsStore(kv jetstream.KeyValue) *NATSFindingsStore {
	return &NATSFindingsStore{kv: kv}
}

func (s *NATSFindingsStore) ShouldEscalate(ctx context.Context, fingerprint string) (bool, error) {
	entry, err := s.kv.Get(ctx, fingerprint)
	if errors.Is(err, jetstream.ErrKeyNotFound) {
		return true, nil
	}
	if err != nil {
		return false, err
	}

	var e natsEntry
	if err := json.Unmarshal(entry.Value(), &e); err != nil {
		return true, nil // corrupted entry, allow re-escalation
	}

	if time.Now().After(e.ExpiresAt) {
		_ = s.kv.Delete(ctx, fingerprint)
		return true, nil
	}
	return false, nil
}

func (s *NATSFindingsStore) MarkEscalated(ctx context.Context, fingerprint string, ttl time.Duration) error {
	data, err := json.Marshal(natsEntry{ExpiresAt: time.Now().Add(ttl)})
	if err != nil {
		return err
	}
	_, err = s.kv.Put(ctx, fingerprint, data)
	return err
}

func (s *NATSFindingsStore) MarkResolved(ctx context.Context, fingerprint string) error {
	return s.kv.Delete(ctx, fingerprint)
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/store_nats.go
git commit -m "feat(cluster-agents): add NATS KV findings store"
```

---

### Task 5: LLM client abstraction

**Files:**

- Create: `services/cluster-agents/llm.go`
- Create: `services/cluster-agents/llm_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLLMClient_Analyze(t *testing.T) {
	// Fake llama.cpp server returning OpenAI-compatible response.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("unexpected content-type: %s", r.Header.Get("Content-Type"))
		}

		resp := ChatCompletionResponse{
			Choices: []Choice{{
				Message: Message{
					Role:    "assistant",
					Content: `[{"severity":"warning","title":"Pod restarting","detail":"nginx-abc restarted 5 times","fingerprint":"patrol:pod:default/nginx-abc:CrashLoopBackOff"}]`,
				},
			}},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewLLMClient(server.URL, "test-model")
	result, err := client.Complete(context.Background(), "system prompt", "user prompt")
	if err != nil {
		t.Fatal(err)
	}
	if result == "" {
		t.Error("expected non-empty result")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestLLMClient -v`
Expected: FAIL — `NewLLMClient` undefined

**Step 3: Write llm.go**

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// LLMClient sends prompts to an OpenAI-compatible API (llama.cpp).
type LLMClient struct {
	baseURL string
	model   string
	client  *http.Client
}

type ChatCompletionRequest struct {
	Model       string    `json:"model"`
	Messages    []Message `json:"messages"`
	Temperature float64   `json:"temperature"`
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatCompletionResponse struct {
	Choices []Choice `json:"choices"`
}

type Choice struct {
	Message Message `json:"message"`
}

func NewLLMClient(baseURL, model string) *LLMClient {
	return &LLMClient{
		baseURL: baseURL,
		model:   model,
		client:  &http.Client{Timeout: 120 * time.Second},
	}
}

// Complete sends a system+user prompt and returns the assistant response.
func (c *LLMClient) Complete(ctx context.Context, system, user string) (string, error) {
	req := ChatCompletionRequest{
		Model:       c.model,
		Temperature: 0.1,
		Messages: []Message{
			{Role: "system", Content: system},
			{Role: "user", Content: user},
		},
	}

	body, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("llm request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("llm returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result ChatCompletionResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	if len(result.Choices) == 0 {
		return "", fmt.Errorf("llm returned no choices")
	}

	return result.Choices[0].Message.Content, nil
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestLLMClient -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/llm.go services/cluster-agents/llm_test.go
git commit -m "feat(cluster-agents): add LLM client for llama.cpp"
```

---

### Task 6: Kubernetes collector

**Files:**

- Create: `services/cluster-agents/collector_k8s.go`
- Create: `services/cluster-agents/collector_k8s_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestK8sCollector_FindsCrashLooping(t *testing.T) {
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "bad-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodRunning,
			ContainerStatuses: []corev1.ContainerStatus{{
				Name:         "app",
				RestartCount: 10,
				Ready:        false,
				State: corev1.ContainerState{
					Waiting: &corev1.ContainerStateWaiting{
						Reason: "CrashLoopBackOff",
					},
				},
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Source == "k8s:pod" && f.Title == "Container CrashLoopBackOff" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected CrashLoopBackOff finding, got %d findings: %+v", len(findings), findings)
	}
}

func TestK8sCollector_FindsNotReady(t *testing.T) {
	notReadyTime := metav1.NewTime(time.Now().Add(-10 * time.Minute))
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "slow-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodPending,
			Conditions: []corev1.PodCondition{{
				Type:               corev1.PodReady,
				Status:             corev1.ConditionFalse,
				LastTransitionTime: notReadyTime,
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Source == "k8s:pod" && f.Title == "Pod not ready" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected not-ready finding, got %d findings: %+v", len(findings), findings)
	}
}

func TestK8sCollector_HealthyPodsNoFindings(t *testing.T) {
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "good-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodRunning,
			ContainerStatuses: []corev1.ContainerStatus{{
				Name:         "app",
				RestartCount: 0,
				Ready:        true,
				State: corev1.ContainerState{
					Running: &corev1.ContainerStateRunning{},
				},
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected no findings for healthy pod, got %d: %+v", len(findings), findings)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestK8sCollector -v`
Expected: FAIL — `NewK8sCollector` undefined

**Step 3: Write collector_k8s.go**

```go
package main

import (
	"context"
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

const (
	restartThreshold = 3
	notReadyTimeout  = 5 * time.Minute
)

// K8sCollector gathers pod and node health findings from the Kubernetes API.
type K8sCollector struct {
	client kubernetes.Interface
}

func NewK8sCollector(client kubernetes.Interface) *K8sCollector {
	return &K8sCollector{client: client}
}

func (c *K8sCollector) Collect(ctx context.Context) ([]Finding, error) {
	var findings []Finding

	podFindings, err := c.collectPods(ctx)
	if err != nil {
		return nil, fmt.Errorf("collect pods: %w", err)
	}
	findings = append(findings, podFindings...)

	nodeFindings, err := c.collectNodes(ctx)
	if err != nil {
		return nil, fmt.Errorf("collect nodes: %w", err)
	}
	findings = append(findings, nodeFindings...)

	return findings, nil
}

func (c *K8sCollector) collectPods(ctx context.Context) ([]Finding, error) {
	pods, err := c.client.CoreV1().Pods("").List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}

	var findings []Finding
	now := time.Now()

	for _, pod := range pods.Items {
		// Check container statuses for crash loops and high restarts.
		for _, cs := range pod.Status.ContainerStatuses {
			if cs.State.Waiting != nil && cs.State.Waiting.Reason == "CrashLoopBackOff" {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:CrashLoopBackOff", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityCritical,
					Title:       "Container CrashLoopBackOff",
					Detail:      fmt.Sprintf("%s/%s container %s is crash-looping (restarts: %d)", pod.Namespace, pod.Name, cs.Name, cs.RestartCount),
					Data: map[string]any{
						"namespace":    pod.Namespace,
						"pod":          pod.Name,
						"container":    cs.Name,
						"restartCount": cs.RestartCount,
					},
					Timestamp: now,
				})
			} else if cs.RestartCount >= restartThreshold && !cs.Ready {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:HighRestarts", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityWarning,
					Title:       "Container restarting frequently",
					Detail:      fmt.Sprintf("%s/%s container %s has restarted %d times", pod.Namespace, pod.Name, cs.Name, cs.RestartCount),
					Data: map[string]any{
						"namespace":    pod.Namespace,
						"pod":          pod.Name,
						"container":    cs.Name,
						"restartCount": cs.RestartCount,
					},
					Timestamp: now,
				})
			}

			// Check for OOMKilled.
			if cs.LastTerminationState.Terminated != nil && cs.LastTerminationState.Terminated.Reason == "OOMKilled" {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:OOMKilled", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityWarning,
					Title:       "Container OOMKilled",
					Detail:      fmt.Sprintf("%s/%s container %s was OOMKilled", pod.Namespace, pod.Name, cs.Name),
					Data: map[string]any{
						"namespace": pod.Namespace,
						"pod":       pod.Name,
						"container": cs.Name,
					},
					Timestamp: now,
				})
			}
		}

		// Check for pods not ready beyond timeout.
		for _, cond := range pod.Status.Conditions {
			if cond.Type == corev1.PodReady && cond.Status == corev1.ConditionFalse {
				if now.Sub(cond.LastTransitionTime.Time) > notReadyTimeout {
					findings = append(findings, Finding{
						Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:NotReady", pod.Namespace, pod.Name),
						Source:      "k8s:pod",
						Severity:    SeverityWarning,
						Title:       "Pod not ready",
						Detail:      fmt.Sprintf("%s/%s has been not-ready for %s", pod.Namespace, pod.Name, now.Sub(cond.LastTransitionTime.Time).Round(time.Minute)),
						Data: map[string]any{
							"namespace": pod.Namespace,
							"pod":       pod.Name,
							"phase":     string(pod.Status.Phase),
						},
						Timestamp: now,
					})
				}
			}
		}
	}

	return findings, nil
}

func (c *K8sCollector) collectNodes(ctx context.Context) ([]Finding, error) {
	nodes, err := c.client.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}

	var findings []Finding
	now := time.Now()

	pressureConditions := map[corev1.NodeConditionType]bool{
		corev1.NodeMemoryPressure: true,
		corev1.NodeDiskPressure:   true,
		corev1.NodePIDPressure:    true,
	}

	for _, node := range nodes.Items {
		// Check for node not ready.
		for _, cond := range node.Status.Conditions {
			if cond.Type == corev1.NodeReady && cond.Status != corev1.ConditionTrue {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:node:%s:NotReady", node.Name),
					Source:      "k8s:node",
					Severity:    SeverityCritical,
					Title:       "Node not ready",
					Detail:      fmt.Sprintf("Node %s is not ready: %s", node.Name, cond.Message),
					Data:        map[string]any{"node": node.Name, "reason": cond.Reason},
					Timestamp:   now,
				})
			}

			// Check for pressure conditions.
			if pressureConditions[cond.Type] && cond.Status == corev1.ConditionTrue {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:node:%s:%s", node.Name, cond.Type),
					Source:      "k8s:node",
					Severity:    SeverityWarning,
					Title:       fmt.Sprintf("Node %s", cond.Type),
					Detail:      fmt.Sprintf("Node %s has %s: %s", node.Name, cond.Type, cond.Message),
					Data:        map[string]any{"node": node.Name, "condition": string(cond.Type)},
					Timestamp:   now,
				})
			}
		}
	}

	return findings, nil
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestK8sCollector -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/collector_k8s.go services/cluster-agents/collector_k8s_test.go
git commit -m "feat(cluster-agents): add Kubernetes pod and node collector"
```

---

### Task 7: ArgoCD collector

**Files:**

- Create: `services/cluster-agents/collector_argocd.go`
- Create: `services/cluster-agents/collector_argocd_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestArgoCDCollector_FindsDegraded(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ArgoCDAppList{
			Items: []ArgoCDApp{
				{
					Metadata: ArgoCDMetadata{Name: "my-app"},
					Status: ArgoCDAppStatus{
						Health: ArgoCDHealth{Status: "Degraded"},
						Sync:   ArgoCDSync{Status: "Synced"},
					},
				},
				{
					Metadata: ArgoCDMetadata{Name: "healthy-app"},
					Status: ArgoCDAppStatus{
						Health: ArgoCDHealth{Status: "Healthy"},
						Sync:   ArgoCDSync{Status: "Synced"},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewArgoCDCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d: %+v", len(findings), findings)
	}
	if findings[0].Title != "ArgoCD app Degraded" {
		t.Errorf("unexpected title: %s", findings[0].Title)
	}
}

func TestArgoCDCollector_FindsOutOfSync(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ArgoCDAppList{
			Items: []ArgoCDApp{{
				Metadata: ArgoCDMetadata{Name: "drifted-app"},
				Status: ArgoCDAppStatus{
					Health: ArgoCDHealth{Status: "Healthy"},
					Sync:   ArgoCDSync{Status: "OutOfSync"},
				},
			}},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewArgoCDCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(findings))
	}
	if findings[0].Severity != SeverityWarning {
		t.Errorf("expected warning severity, got %s", findings[0].Severity)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestArgoCDCollector -v`
Expected: FAIL — `NewArgoCDCollector` undefined

**Step 3: Write collector_argocd.go**

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// ArgoCD API response types.
type ArgoCDAppList struct {
	Items []ArgoCDApp `json:"items"`
}

type ArgoCDApp struct {
	Metadata ArgoCDMetadata  `json:"metadata"`
	Status   ArgoCDAppStatus `json:"status"`
}

type ArgoCDMetadata struct {
	Name string `json:"name"`
}

type ArgoCDAppStatus struct {
	Health ArgoCDHealth `json:"health"`
	Sync   ArgoCDSync   `json:"sync"`
}

type ArgoCDHealth struct {
	Status string `json:"status"`
}

type ArgoCDSync struct {
	Status string `json:"status"`
}

// ArgoCDCollector checks ArgoCD application health and sync status.
type ArgoCDCollector struct {
	baseURL string
	token   string
	client  *http.Client
}

func NewArgoCDCollector(baseURL, token string) *ArgoCDCollector {
	return &ArgoCDCollector{
		baseURL: baseURL,
		token:   token,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *ArgoCDCollector) Collect(ctx context.Context) ([]Finding, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/applications", nil)
	if err != nil {
		return nil, err
	}
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("argocd list apps: %w", err)
	}
	defer resp.Body.Close()

	var apps ArgoCDAppList
	if err := json.NewDecoder(resp.Body).Decode(&apps); err != nil {
		return nil, fmt.Errorf("decode argocd response: %w", err)
	}

	var findings []Finding
	now := time.Now()

	unhealthyStatuses := map[string]Severity{
		"Degraded":    SeverityCritical,
		"Missing":     SeverityCritical,
		"Unknown":     SeverityWarning,
		"Suspended":   SeverityInfo,
		"Progressing": SeverityInfo,
	}

	for _, app := range apps.Items {
		if sev, bad := unhealthyStatuses[app.Status.Health.Status]; bad && sev != SeverityInfo {
			findings = append(findings, Finding{
				Fingerprint: fmt.Sprintf("patrol:argocd:%s:health:%s", app.Metadata.Name, app.Status.Health.Status),
				Source:      "argocd",
				Severity:    sev,
				Title:       fmt.Sprintf("ArgoCD app %s", app.Status.Health.Status),
				Detail:      fmt.Sprintf("Application %s health is %s", app.Metadata.Name, app.Status.Health.Status),
				Data:        map[string]any{"app": app.Metadata.Name, "health": app.Status.Health.Status, "sync": app.Status.Sync.Status},
				Timestamp:   now,
			})
		}

		if app.Status.Sync.Status == "OutOfSync" {
			findings = append(findings, Finding{
				Fingerprint: fmt.Sprintf("patrol:argocd:%s:sync:OutOfSync", app.Metadata.Name),
				Source:      "argocd",
				Severity:    SeverityWarning,
				Title:       "ArgoCD app OutOfSync",
				Detail:      fmt.Sprintf("Application %s is out of sync", app.Metadata.Name),
				Data:        map[string]any{"app": app.Metadata.Name, "health": app.Status.Health.Status, "sync": app.Status.Sync.Status},
				Timestamp:   now,
			})
		}
	}

	return findings, nil
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestArgoCDCollector -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/collector_argocd.go services/cluster-agents/collector_argocd_test.go
git commit -m "feat(cluster-agents): add ArgoCD health and sync collector"
```

---

### Task 8: Escalation handlers

**Files:**

- Create: `services/cluster-agents/escalator.go`
- Create: `services/cluster-agents/escalator_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestEscalator_RoutesInfoToLog(t *testing.T) {
	store := NewMemFindingsStore()
	escalator := NewEscalator(store, nil, nil)

	actions := []Action{{
		Type: ActionLog,
		Finding: Finding{
			Fingerprint: "fp-1",
			Severity:    SeverityInfo,
			Title:       "test info",
		},
	}}

	// Should not error — logs are fire-and-forget.
	err := escalator.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}
}

func TestEscalator_SubmitsOrchestratorJob(t *testing.T) {
	var received map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&received)
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-123"})
	}))
	defer server.Close()

	store := NewMemFindingsStore()
	escalator := NewEscalator(store, nil, &OrchestratorClient{baseURL: server.URL, client: &http.Client{}})

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "fp-critical",
			Severity:    SeverityCritical,
			Title:       "Pod crash-looping",
			Detail:      "default/my-pod is crash-looping",
		},
	}}

	err := escalator.Execute(context.Background(), actions)
	if err != nil {
		t.Fatal(err)
	}

	if received["task"] == nil || received["task"] == "" {
		t.Error("expected task to be set in orchestrator request")
	}
}

func TestEscalator_DeduplicatesFindings(t *testing.T) {
	store := NewMemFindingsStore()
	var callCount int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(map[string]string{"id": "job-123"})
	}))
	defer server.Close()

	escalator := NewEscalator(store, nil, &OrchestratorClient{baseURL: server.URL, client: &http.Client{}})

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "fp-dedup",
			Severity:    SeverityCritical,
			Title:       "same issue",
		},
	}}

	// First call should escalate.
	escalator.Execute(context.Background(), actions)
	// Second call should be deduped.
	escalator.Execute(context.Background(), actions)

	if callCount != 1 {
		t.Errorf("expected 1 orchestrator call (dedup), got %d", callCount)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestEscalator -v`
Expected: FAIL — `NewEscalator` undefined

**Step 3: Write escalator.go**

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// OrchestratorClient submits jobs to the agent-orchestrator API.
type OrchestratorClient struct {
	baseURL string
	client  *http.Client
}

func NewOrchestratorClient(baseURL string) *OrchestratorClient {
	return &OrchestratorClient{
		baseURL: baseURL,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

// GitHubClient creates issues via the GitHub API.
type GitHubClient struct {
	token string
	repo  string
	client *http.Client
}

func NewGitHubClient(token, repo string) *GitHubClient {
	return &GitHubClient{
		token:  token,
		repo:   repo,
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

// Escalator routes actions to their appropriate handlers with deduplication.
type Escalator struct {
	store        FindingsStore
	github       *GitHubClient
	orchestrator *OrchestratorClient
	findingTTL   time.Duration
}

func NewEscalator(store FindingsStore, github *GitHubClient, orchestrator *OrchestratorClient) *Escalator {
	return &Escalator{
		store:        store,
		github:       github,
		orchestrator: orchestrator,
		findingTTL:   24 * time.Hour,
	}
}

func (e *Escalator) Execute(ctx context.Context, actions []Action) error {
	for _, action := range actions {
		if action.Type == ActionLog {
			slog.Info("finding",
				"severity", action.Finding.Severity,
				"title", action.Finding.Title,
				"detail", action.Finding.Detail,
				"fingerprint", action.Finding.Fingerprint,
			)
			continue
		}

		ok, err := e.store.ShouldEscalate(ctx, action.Finding.Fingerprint)
		if err != nil {
			slog.Error("dedup check failed", "error", err, "fingerprint", action.Finding.Fingerprint)
			continue
		}
		if !ok {
			slog.Debug("skipping duplicate finding", "fingerprint", action.Finding.Fingerprint)
			continue
		}

		switch action.Type {
		case ActionGitHubIssue:
			if err := e.createGitHubIssue(ctx, action); err != nil {
				slog.Error("github issue failed", "error", err)
				continue
			}
		case ActionOrchestratorJob:
			if err := e.submitOrchestratorJob(ctx, action); err != nil {
				slog.Error("orchestrator job failed", "error", err)
				continue
			}
		}

		e.store.MarkEscalated(ctx, action.Finding.Fingerprint, e.findingTTL)
	}
	return nil
}

func (e *Escalator) submitOrchestratorJob(ctx context.Context, action Action) error {
	task := fmt.Sprintf("Cluster Patrol detected an issue that needs investigation and remediation.\n\n"+
		"**Issue:** %s\n\n"+
		"**Details:** %s\n\n"+
		"**Severity:** %s\n\n"+
		"Investigate this issue using MCP tools. If a GitOps change can fix it, create a PR. "+
		"If it requires manual intervention, create a GitHub issue with your findings.",
		action.Finding.Title, action.Finding.Detail, action.Finding.Severity)

	body, _ := json.Marshal(map[string]any{
		"task":   task,
		"source": "cluster-patrol",
	})

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, e.orchestrator.baseURL+"/jobs", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.orchestrator.client.Do(req)
	if err != nil {
		return fmt.Errorf("submit job: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	slog.Info("submitted orchestrator job",
		"fingerprint", action.Finding.Fingerprint,
		"title", action.Finding.Title,
	)
	return nil
}

func (e *Escalator) createGitHubIssue(ctx context.Context, action Action) error {
	if e.github == nil {
		slog.Warn("github client not configured, skipping issue creation")
		return nil
	}

	body, _ := json.Marshal(map[string]any{
		"title": fmt.Sprintf("[cluster-patrol] %s", action.Finding.Title),
		"body": fmt.Sprintf("## Cluster Patrol Finding\n\n"+
			"**Severity:** %s\n"+
			"**Source:** %s\n"+
			"**Fingerprint:** `%s`\n\n"+
			"### Details\n\n%s\n\n"+
			"---\n_Auto-created by cluster-patrol agent_",
			action.Finding.Severity, action.Finding.Source,
			action.Finding.Fingerprint, action.Finding.Detail),
		"labels": []string{"cluster-patrol", string(action.Finding.Severity)},
	})

	url := fmt.Sprintf("https://api.github.com/repos/%s/issues", e.github.repo)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+e.github.token)
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.github.client.Do(req)
	if err != nil {
		return fmt.Errorf("create issue: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("github returned %d", resp.StatusCode)
	}

	slog.Info("created github issue",
		"fingerprint", action.Finding.Fingerprint,
		"title", action.Finding.Title,
	)
	return nil
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestEscalator -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/escalator.go services/cluster-agents/escalator_test.go
git commit -m "feat(cluster-agents): add escalation handlers with dedup"
```

---

### Task 9: Patrol agent — wiring Collect → Analyze → Execute

**Files:**

- Create: `services/cluster-agents/patrol.go`
- Create: `services/cluster-agents/patrol_test.go`

**Step 1: Write the failing test**

```go
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPatrolAgent_AnalyzesFindings(t *testing.T) {
	// Fake LLM that classifies findings.
	llmServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ChatCompletionResponse{
			Choices: []Choice{{
				Message: Message{
					Content: `[{"action_type":"orchestrator_job","finding_fingerprint":"patrol:pod:default/bad:CrashLoopBackOff","severity":"critical"}]`,
				},
			}},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer llmServer.Close()

	findings := []Finding{{
		Fingerprint: "patrol:pod:default/bad:CrashLoopBackOff",
		Source:      "k8s:pod",
		Severity:    SeverityCritical,
		Title:       "Container CrashLoopBackOff",
		Detail:      "default/bad container app is crash-looping",
	}}

	llm := NewLLMClient(llmServer.URL, "test-model")
	patrol := &PatrolAgent{
		llm:      llm,
		interval: 5 * time.Minute,
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}

	if len(actions) == 0 {
		t.Fatal("expected at least one action")
	}
	if actions[0].Type != ActionOrchestratorJob {
		t.Errorf("expected orchestrator_job action, got %s", actions[0].Type)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd services/cluster-agents && go test -run TestPatrolAgent -v`
Expected: FAIL — `PatrolAgent` undefined

**Step 3: Write patrol.go**

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"
)

const patrolSystemPrompt = `You are a Kubernetes cluster health analyzer. You receive structured findings from cluster monitoring and must classify them into actions.

For each finding, decide the appropriate action:
- "log" — informational, no action needed (normal churn, expected behavior)
- "github_issue" — warning that should be tracked but doesn't need immediate automated remediation
- "orchestrator_job" — critical issue that an AI agent should investigate and attempt to fix

Respond with a JSON array of action objects:
[{"action_type": "log|github_issue|orchestrator_job", "finding_fingerprint": "...", "severity": "info|warning|critical", "reasoning": "brief explanation"}]

Consider correlations between findings. Multiple related issues may indicate a root cause worth escalating even if individual findings seem minor.

IMPORTANT: Be conservative with orchestrator_job — only use it for issues that are clearly actionable and fixable via GitOps changes or known remediation steps. Do not escalate transient issues.`

// PatrolAgent implements the cluster patrol loop.
type PatrolAgent struct {
	collectors []collector
	llm        *LLMClient
	escalator  *Escalator
	interval   time.Duration
}

type collector interface {
	Collect(ctx context.Context) ([]Finding, error)
}

type llmAction struct {
	ActionType         string `json:"action_type"`
	FindingFingerprint string `json:"finding_fingerprint"`
	Severity           string `json:"severity"`
	Reasoning          string `json:"reasoning"`
}

func NewPatrolAgent(collectors []collector, llm *LLMClient, escalator *Escalator, interval time.Duration) *PatrolAgent {
	return &PatrolAgent{
		collectors: collectors,
		llm:        llm,
		escalator:  escalator,
		interval:   interval,
	}
}

func (p *PatrolAgent) Name() string            { return "cluster-patrol" }
func (p *PatrolAgent) Interval() time.Duration { return p.interval }

func (p *PatrolAgent) Collect(ctx context.Context) ([]Finding, error) {
	var all []Finding
	for _, c := range p.collectors {
		findings, err := c.Collect(ctx)
		if err != nil {
			slog.Error("collector failed", "error", err)
			continue // Don't fail the whole sweep for one collector.
		}
		all = append(all, findings...)
	}
	return all, nil
}

func (p *PatrolAgent) Analyze(ctx context.Context, findings []Finding) ([]Action, error) {
	if len(findings) == 0 {
		return nil, nil
	}

	findingsJSON, err := json.Marshal(findings)
	if err != nil {
		return nil, fmt.Errorf("marshal findings: %w", err)
	}

	response, err := p.llm.Complete(ctx, patrolSystemPrompt, string(findingsJSON))
	if err != nil {
		return nil, fmt.Errorf("llm analysis: %w", err)
	}

	var llmActions []llmAction
	if err := json.Unmarshal([]byte(response), &llmActions); err != nil {
		slog.Error("failed to parse LLM response", "response", response, "error", err)
		return nil, fmt.Errorf("parse llm response: %w", err)
	}

	// Build a lookup of findings by fingerprint.
	findingMap := make(map[string]Finding, len(findings))
	for _, f := range findings {
		findingMap[f.Fingerprint] = f
	}

	var actions []Action
	for _, la := range llmActions {
		finding, ok := findingMap[la.FindingFingerprint]
		if !ok {
			slog.Warn("LLM referenced unknown fingerprint", "fingerprint", la.FindingFingerprint)
			continue
		}

		var actionType ActionType
		switch la.ActionType {
		case "log":
			actionType = ActionLog
		case "github_issue":
			actionType = ActionGitHubIssue
		case "orchestrator_job":
			actionType = ActionOrchestratorJob
		default:
			slog.Warn("unknown action type from LLM", "type", la.ActionType)
			continue
		}

		actions = append(actions, Action{
			Type:    actionType,
			Finding: finding,
			Payload: map[string]any{"reasoning": la.Reasoning},
		})
	}

	return actions, nil
}

func (p *PatrolAgent) Execute(ctx context.Context, actions []Action) error {
	return p.escalator.Execute(ctx, actions)
}
```

**Step 4: Run tests to verify they pass**

Run: `cd services/cluster-agents && go test -run TestPatrolAgent -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/cluster-agents/patrol.go services/cluster-agents/patrol_test.go
git commit -m "feat(cluster-agents): add patrol agent with LLM analysis"
```

---

### Task 10: Wire up main.go and add health endpoint

**Files:**

- Modify: `services/cluster-agents/main.go`

**Step 1: Update main.go to wire everything together**

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Configuration from environment.
	natsURL := envOr("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")
	llmURL := envOr("LLM_URL", "http://llama-cpp.llama-cpp.svc.cluster.local:8080")
	llmModel := envOr("LLM_MODEL", "default")
	argocdURL := envOr("ARGOCD_URL", "http://argocd-server.argocd.svc.cluster.local")
	argocdToken := os.Getenv("ARGOCD_TOKEN")
	orchestratorURL := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080")
	githubToken := os.Getenv("GITHUB_TOKEN")
	githubRepo := envOr("GITHUB_REPO", "jomcgi/homelab")
	httpPort := envOr("HTTP_PORT", "8080")
	patrolInterval := envDurationOr("PATROL_INTERVAL", 5*time.Minute)

	// Connect to NATS.
	nc, err := nats.Connect(natsURL)
	if err != nil {
		slog.Error("failed to connect to NATS", "error", err)
		os.Exit(1)
	}
	defer nc.Close()

	js, err := jetstream.New(nc)
	if err != nil {
		slog.Error("failed to create jetstream context", "error", err)
		os.Exit(1)
	}

	// Create findings KV bucket.
	kv, err := js.CreateOrUpdateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: "cluster-agents-findings",
		TTL:    48 * time.Hour,
	})
	if err != nil {
		slog.Error("failed to create KV bucket", "error", err)
		os.Exit(1)
	}

	// Kubernetes client.
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		slog.Error("failed to get in-cluster config", "error", err)
		os.Exit(1)
	}
	k8sClient, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		slog.Error("failed to create kubernetes client", "error", err)
		os.Exit(1)
	}

	// Build components.
	store := NewNATSFindingsStore(kv)
	llm := NewLLMClient(llmURL, llmModel)

	var github *GitHubClient
	if githubToken != "" {
		github = NewGitHubClient(githubToken, githubRepo)
	}
	orchestrator := NewOrchestratorClient(orchestratorURL)
	escalator := NewEscalator(store, github, orchestrator)

	// Build collectors.
	collectors := []collector{
		NewK8sCollector(k8sClient),
		NewArgoCDCollector(argocdURL, argocdToken),
	}

	// Build agents.
	patrol := NewPatrolAgent(collectors, llm, escalator, patrolInterval)
	runner := NewRunner([]Agent{patrol})

	// Health endpoint.
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})

	srv := &http.Server{Addr: ":" + httpPort, Handler: mux}
	go func() {
		slog.Info("http server starting", "port", httpPort)
		if err := srv.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("http server error", "error", err)
		}
	}()

	slog.Info("cluster-agents starting", "patrol_interval", patrolInterval)
	runner.Run(ctx)

	srv.Shutdown(context.Background())
	slog.Info("cluster-agents stopped")
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envDurationOr(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			slog.Warn("invalid duration, using default", "key", key, "value", v, "default", fallback)
			return fallback
		}
		return d
	}
	return fallback
}
```

**Step 2: Commit**

```bash
git add services/cluster-agents/main.go
git commit -m "feat(cluster-agents): wire main with all components"
```

---

## Phase 2: Deployment Infrastructure (Tasks 11-14)

### Task 11: Bazel BUILD file

**Files:**

- Create: `services/cluster-agents/BUILD`

**Step 1: Create BUILD file**

Follow the exact pattern from `services/agent-orchestrator/BUILD`. Use `go_library` + `go_binary` + `go_test` + `go_image`.

```starlark
load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cluster-agents_lib",
    srcs = [
        "collector_argocd.go",
        "collector_k8s.go",
        "escalator.go",
        "llm.go",
        "main.go",
        "model.go",
        "patrol.go",
        "runner.go",
        "store.go",
        "store_nats.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/cluster-agents",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
    ],
)

go_binary(
    name = "cluster-agents",
    embed = [":cluster-agents_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "cluster-agents_unit_test",
    srcs = [
        "collector_argocd_test.go",
        "collector_k8s_test.go",
        "escalator_test.go",
        "llm_test.go",
        "patrol_test.go",
        "runner_test.go",
        "store_test.go",
    ],
    embed = [":cluster-agents_lib"],
    deps = [
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes/fake",
    ],
)

go_image(
    name = "image",
    binary = ":cluster-agents",
    repository = "ghcr.io/jomcgi/homelab/services/cluster-agents",
)
```

**Step 2: Run `format` to validate and update BUILD**

Run: `format`
This will run gazelle to verify dependencies are correct and fix any issues.

**Step 3: Commit**

```bash
git add services/cluster-agents/BUILD
git commit -m "build(cluster-agents): add Bazel BUILD file"
```

---

### Task 12: Helm chart

**Files:**

- Create: `charts/cluster-agents/Chart.yaml`
- Create: `charts/cluster-agents/values.yaml`
- Create: `charts/cluster-agents/templates/_helpers.tpl`
- Create: `charts/cluster-agents/templates/deployment.yaml`
- Create: `charts/cluster-agents/templates/service.yaml`
- Create: `charts/cluster-agents/templates/serviceaccount.yaml`
- Create: `charts/cluster-agents/templates/rbac.yaml`

Mirror the `charts/agent-orchestrator/` chart structure. Key differences:

- ClusterRole (not Role) with read-only access to pods, nodes, events across all namespaces
- Config section maps to env vars: `NATS_URL`, `LLM_URL`, `LLM_MODEL`, `ARGOCD_URL`, `ORCHESTRATOR_URL`, `PATROL_INTERVAL`, `HTTP_PORT`
- Secrets for `GITHUB_TOKEN` and `ARGOCD_TOKEN` via 1Password

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: cluster-agents
description: Autonomous cluster monitoring agents
version: 0.1.0
appVersion: "0.1.0"
```

**Step 2: Create values.yaml**

```yaml
replicaCount: 1

image:
  repository: ghcr.io/jomcgi/homelab/services/cluster-agents
  tag: main
  pullPolicy: IfNotPresent

imagePullSecret:
  enabled: false
  create: true
  onepassword:
    itemPath: "vaults/k8s-homelab/items/ghcr-read-permissions"

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
    cpu: 200m
    memory: 256Mi

config:
  natsUrl: "nats://nats.nats.svc.cluster.local:4222"
  llmUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"
  llmModel: "default"
  argocdUrl: "http://argocd-server.argocd.svc.cluster.local"
  orchestratorUrl: "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080"
  githubRepo: "jomcgi/homelab"
  httpPort: "8080"
  patrolInterval: "5m"

secrets:
  githubToken:
    onepassword:
      itemPath: "vaults/k8s-homelab/items/github-token-cluster-agents"
  argocdToken:
    onepassword:
      itemPath: "vaults/k8s-homelab/items/argocd-token-cluster-agents"

podAnnotations: {}
```

**Step 3: Create templates** following `charts/agent-orchestrator/templates/` patterns exactly.

Key template differences from agent-orchestrator:

- `rbac.yaml`: Use `ClusterRole` + `ClusterRoleBinding` for read-only access across namespaces
- `deployment.yaml`: Add secret env vars for `GITHUB_TOKEN` and `ARGOCD_TOKEN` from 1Password-backed secrets
- No sandbox namespace RBAC needed

**ClusterRole rules:**

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes", "events", "namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
```

**Step 4: Validate with helm template**

Run: `helm template cluster-agents charts/cluster-agents/`
Expected: Valid YAML output with all resources

**Step 5: Commit**

```bash
git add charts/cluster-agents/
git commit -m "feat(cluster-agents): add Helm chart"
```

---

### Task 13: ArgoCD overlay

**Files:**

- Create: `overlays/prod/cluster-agents/application.yaml`
- Create: `overlays/prod/cluster-agents/kustomization.yaml`
- Create: `overlays/prod/cluster-agents/values.yaml`
- Create: `overlays/prod/cluster-agents/imageupdater.yaml`
- Modify: `overlays/prod/kustomization.yaml` — add `cluster-agents` to resources list

Follow the exact pattern from `overlays/prod/agent-orchestrator/`.

**Step 1: Create application.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: prod-cluster-agents
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/cluster-agents
    targetRevision: HEAD
    helm:
      releaseName: cluster-agents
      valueFiles:
        - values.yaml
        - ../../overlays/prod/cluster-agents/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: cluster-agents
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
```

**Step 3: Create values.yaml** with prod overrides (image pull secret, OTel annotations, image digest)

**Step 4: Create imageupdater.yaml** following agent-orchestrator pattern

**Step 5: Add to overlays/prod/kustomization.yaml resources list**

**Step 6: Validate**

Run: `helm template cluster-agents charts/cluster-agents/ -f overlays/prod/cluster-agents/values.yaml`
Expected: Valid YAML

**Step 7: Commit**

```bash
git add overlays/prod/cluster-agents/ overlays/prod/kustomization.yaml
git commit -m "feat(cluster-agents): add prod ArgoCD overlay"
```

---

### Task 14: Add OTel namespace and HTTP check alert

**Files:**

- Modify: `overlays/cluster-critical/opentelemetry-operator/values.yaml` — add `cluster-agents` to instrumentation namespaces
- Create: `overlays/prod/cluster-agents/httpcheck-alert.yaml` — HTTP check alert for the service

Follow the patterns from existing httpcheck alerts (e.g., `overlays/cluster-critical/argocd/argocd-httpcheck-alert.yaml`) and the add-httpcheck-alert skill.

**Step 1: Add namespace to OTel operator config**

Add `cluster-agents` to the `namespaces` list in `overlays/cluster-critical/opentelemetry-operator/values.yaml`.

**Step 2: Create httpcheck alert ConfigMap**

Follow existing httpcheck alert pattern for the `/health` endpoint.

**Step 3: Commit**

```bash
git add overlays/cluster-critical/opentelemetry-operator/values.yaml overlays/prod/cluster-agents/httpcheck-alert.yaml
git commit -m "feat(cluster-agents): add OTel instrumentation and health check alert"
```

---

## Phase 3: Future Agents (Not in this PR)

These are documented for future implementation:

### PR Reviewer Agent

- **Collector**: GitHub API — polls for open PRs matching criteria
- **Analyzer**: llama.cpp for convention checks, Claude for complex review
- **Escalation**: Approve + merge or request changes with comments
- **Files**: `services/cluster-agents/agent_pr_reviewer.go`

### SigNoz Log Anomaly Collector

- **Collector**: SigNoz API — checks error rates, log volume spikes
- **Files**: `services/cluster-agents/collector_signoz.go`

### Certificate Expiry Collector

- **Collector**: K8s API — checks TLS secret expiry dates
- **Files**: `services/cluster-agents/collector_certs.go`

---

## Summary

| Task | Component             | Commit message                                                          |
| ---- | --------------------- | ----------------------------------------------------------------------- |
| 1    | Core types + scaffold | `feat(cluster-agents): scaffold service with core types`                |
| 2    | Agent loop runner     | `feat(cluster-agents): add agent loop runner with tests`                |
| 3    | Findings store (mem)  | `feat(cluster-agents): add findings store with dedup and TTL`           |
| 4    | Findings store (NATS) | `feat(cluster-agents): add NATS KV findings store`                      |
| 5    | LLM client            | `feat(cluster-agents): add LLM client for llama.cpp`                    |
| 6    | K8s collector         | `feat(cluster-agents): add Kubernetes pod and node collector`           |
| 7    | ArgoCD collector      | `feat(cluster-agents): add ArgoCD health and sync collector`            |
| 8    | Escalation handlers   | `feat(cluster-agents): add escalation handlers with dedup`              |
| 9    | Patrol agent          | `feat(cluster-agents): add patrol agent with LLM analysis`              |
| 10   | Main wiring           | `feat(cluster-agents): wire main with all components`                   |
| 11   | Bazel BUILD           | `build(cluster-agents): add Bazel BUILD file`                           |
| 12   | Helm chart            | `feat(cluster-agents): add Helm chart`                                  |
| 13   | ArgoCD overlay        | `feat(cluster-agents): add prod ArgoCD overlay`                         |
| 14   | OTel + alerting       | `feat(cluster-agents): add OTel instrumentation and health check alert` |

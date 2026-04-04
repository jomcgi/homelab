package main

// cluster_agents_coverage_test.go – additional coverage for edge cases and
// error paths not reached by the primary test files.
//
// Covered here:
//   collector_alerts.go  – invalid JSON body; firing rule with nil labels; empty state
//   github_client.go     – empty commit list; missing JSON fields in commit
//   runner.go            – collect error skips analyze+execute; analyze partial
//                          actions+error skips execute; zero Interval() panics
//   escalator.go         – malformed JSON from dedup GET; cancelled context on
//                          submit; 202 response missing 'id' field

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// ─────────────────────────────────────────────────────────────────────────────
// collector_alerts.go
// ─────────────────────────────────────────────────────────────────────────────

// TestAlertCollector_InvalidJSONBody verifies that a 200 OK response whose body
// is not valid JSON causes Collect to return a decode error.
func TestAlertCollector_InvalidJSONBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("not-valid-json{{{"))
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "test-token")
	_, err := collector.Collect(context.Background())
	if err == nil {
		t.Fatal("expected decode error for invalid JSON body, got nil")
	}
}

// TestAlertCollector_FiringRuleWithNoLabels verifies that a firing alert rule
// whose Labels map is absent (nil) is still collected. mapSeverity("") returns
// SeverityInfo via the default branch.
func TestAlertCollector_FiringRuleWithNoLabels(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-nolab",
						Name:  "No Labels Alert",
						State: "firing",
						// Labels deliberately omitted (nil map)
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(findings) != 1 {
		t.Fatalf("expected 1 finding for firing rule with no labels, got %d", len(findings))
	}
	if findings[0].Severity != SeverityInfo {
		t.Errorf("expected SeverityInfo for nil labels, got %s", findings[0].Severity)
	}
	if findings[0].Fingerprint != "patrol.alert.rule-nolab" {
		t.Errorf("unexpected fingerprint: %s", findings[0].Fingerprint)
	}
}

// TestAlertCollector_RuleWithEmptyState verifies that a rule whose state is the
// empty string is NOT treated as firing and produces zero findings.
func TestAlertCollector_RuleWithEmptyState(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := alertRulesResponse{
			Status: "success",
			Data: alertRulesData{
				Rules: []alertRule{
					{
						ID:    "rule-empty-state",
						Name:  "Empty State Alert",
						State: "", // neither "firing" nor any other recognised value
						Labels: map[string]string{
							"severity": "critical",
						},
					},
				},
			},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	collector := NewAlertCollector(server.URL, "")
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings for rule with empty state, got %d", len(findings))
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// github_client.go
// ─────────────────────────────────────────────────────────────────────────────

// TestGitHubClient_LatestNonBotCommit_EmptyCommitList verifies that an empty
// commits array returned by the GitHub API results in (nil, nil) — no commit
// found but no error either.
func TestGitHubClient_LatestNonBotCommit_EmptyCommitList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]ghCommit{})
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "tok", "owner/repo")
	commit, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-bot"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if commit != nil {
		t.Errorf("expected nil commit from empty list, got SHA %q", commit.SHA)
	}
}

// TestGitHubClient_LatestNonBotCommit_MissingFields verifies that when the API
// returns a commit whose JSON has no sha/commit fields (zero-value struct), the
// first entry that is not a bot is still returned without an error.
// The author name defaults to "" which is not in botAuthors.
func TestGitHubClient_LatestNonBotCommit_MissingFields(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Encode a commit whose nested fields are absent — JSON decodes to zero values.
		w.Write([]byte(`[{}]`))
	}))
	defer server.Close()

	client := NewGitHubClient(server.URL, "tok", "owner/repo")
	// "ci-bot" is a bot; the empty-string author is not.
	commit, err := client.LatestNonBotCommit(context.Background(), "main", []string{"ci-bot"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if commit == nil {
		t.Fatal("expected non-nil commit for a commit with missing fields that is not a bot")
	}
	// SHA and Author.Name will be zero values ("").
	if commit.SHA != "" {
		t.Errorf("expected empty SHA, got %q", commit.SHA)
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// runner.go — helper agent types (names must not collide with runner_test.go)
// ─────────────────────────────────────────────────────────────────────────────

// collectAlwaysErrorAgent always returns an error from Collect and tracks
// whether Execute was ever called.
type collectAlwaysErrorAgent struct {
	fakeAgent
	executeCount int32 // atomic
}

func (a *collectAlwaysErrorAgent) Collect(_ context.Context) ([]Finding, error) {
	return nil, errors.New("collect always fails")
}

func (a *collectAlwaysErrorAgent) Execute(_ context.Context, _ []Action) error {
	atomic.AddInt32(&a.executeCount, 1)
	return nil
}

// analyzeReturnsActionsAndErrorAgent returns both non-nil actions AND a non-nil
// error from Analyze, and tracks whether Execute was invoked.
type analyzeReturnsActionsAndErrorAgent struct {
	fakeAgent
	executeCount int32 // atomic
}

func (a *analyzeReturnsActionsAndErrorAgent) Analyze(_ context.Context, _ []Finding) ([]Action, error) {
	return []Action{{Type: ActionLog}}, errors.New("partial analyze error")
}

func (a *analyzeReturnsActionsAndErrorAgent) Execute(_ context.Context, _ []Action) error {
	atomic.AddInt32(&a.executeCount, 1)
	return nil
}

// ─────────────────────────────────────────────────────────────────────────────
// runner.go — tests
// ─────────────────────────────────────────────────────────────────────────────

// TestSweep_CollectErrorSkipsAnalyzeAndExecute verifies that when Collect returns
// (nil, error), sweep logs the error and returns without invoking Execute.
func TestSweep_CollectErrorSkipsAnalyzeAndExecute(t *testing.T) {
	agent := &collectAlwaysErrorAgent{
		fakeAgent: fakeAgent{name: "collect-err-agent", interval: 10 * time.Millisecond},
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if atomic.LoadInt32(&agent.executeCount) != 0 {
		t.Errorf("expected Execute never to be called after Collect error, got %d calls",
			atomic.LoadInt32(&agent.executeCount))
	}
}

// TestSweep_AnalyzePartialActionsWithError_ExecuteSkipped verifies that when
// Analyze returns non-nil actions together with a non-nil error, sweep logs the
// error and returns without calling Execute — the partial actions are discarded.
func TestSweep_AnalyzePartialActionsWithError_ExecuteSkipped(t *testing.T) {
	agent := &analyzeReturnsActionsAndErrorAgent{
		fakeAgent: fakeAgent{name: "analyze-partial-err", interval: 10 * time.Millisecond},
	}

	r := &Runner{
		agents:       []Agent{agent},
		sweepTimeout: defaultSweepTimeout,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Millisecond)
	defer cancel()

	r.Run(ctx)

	if atomic.LoadInt32(&agent.executeCount) != 0 {
		t.Errorf("expected Execute to be skipped when Analyze returns an error, got %d calls",
			atomic.LoadInt32(&agent.executeCount))
	}
}

// TestRunAgent_ZeroInterval_Panics verifies that runAgent panics when
// agent.Interval() returns 0 because time.NewTicker requires a positive duration.
// The initial sweep still runs before the panic occurs.
func TestRunAgent_ZeroInterval_Panics(t *testing.T) {
	agent := &fakeAgent{name: "zero-interval", interval: 0}

	r := &Runner{sweepTimeout: 10 * time.Millisecond}

	var panicked bool
	func() {
		defer func() {
			if rec := recover(); rec != nil {
				panicked = true
			}
		}()
		// Cancel the context immediately so the initial sweep returns quickly
		// and the ticker creation (which will panic) is reached promptly.
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		r.runAgent(ctx, agent)
	}()

	if !panicked {
		t.Error("expected runAgent to panic when Interval() == 0 (time.NewTicker requires positive duration)")
	}
	// The initial sweep must have executed before the panic.
	if agent.getSweeps() < 1 {
		t.Error("expected the initial sweep to run before the panic in time.NewTicker")
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// escalator.go
// ─────────────────────────────────────────────────────────────────────────────

// TestEscalator_HasActiveJob_MalformedJSON verifies that when the orchestrator
// dedup endpoint returns 200 OK with malformed JSON, hasActiveJob returns an
// error, the action is skipped via the error-log-and-continue path in Execute,
// and Execute itself returns nil.
func TestEscalator_HasActiveJob_MalformedJSON(t *testing.T) {
	var postCount int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			// 200 OK but body is not valid JSON.
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("not-json"))
			return
		}
		postCount++
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: server.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "test:malformed",
			Source:      "test",
			Title:       "Test",
		},
		Payload: map[string]any{"task": "test task"},
	}}

	err := esc.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("Execute should return nil even after dedup JSON error, got: %v", err)
	}
	if postCount != 0 {
		t.Errorf("expected no POST when dedup check fails (malformed JSON), got %d", postCount)
	}
}

// TestEscalator_SubmitJob_CancelledContext verifies that submitOrchestratorJob
// returns an error when the context is already cancelled, because the HTTP
// client rejects the request.
func TestEscalator_SubmitJob_CancelledContext(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Should not be reached when context is pre-cancelled.
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: server.URL, client: &http.Client{}},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before making the call

	action := Action{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "test:cancel",
			Source:      "test",
			Title:       "Cancelled",
		},
		Payload: map[string]any{"task": "cancelled task"},
	}

	err := esc.submitOrchestratorJob(ctx, action, "test:cancel")
	if err == nil {
		t.Error("expected error from submitOrchestratorJob with cancelled context, got nil")
	}
}

// TestEscalator_SubmitJob_ResponseMissingIDField verifies that a 202 response
// whose JSON body contains no 'id' field is still treated as a successful
// submission — the code only checks the status code, not the response body.
func TestEscalator_SubmitJob_ResponseMissingIDField(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			// No active jobs — dedup passes.
			json.NewEncoder(w).Encode(orchestratorListResponse{Total: 0})
			return
		}
		// 202 with an empty JSON object (no 'id' field).
		w.WriteHeader(http.StatusAccepted)
		w.Write([]byte(`{}`))
	}))
	defer server.Close()

	esc := &Escalator{
		orchestrator: &OrchestratorClient{baseURL: server.URL, client: &http.Client{}},
	}

	actions := []Action{{
		Type: ActionOrchestratorJob,
		Finding: Finding{
			Fingerprint: "test:noid",
			Source:      "test",
			Title:       "No ID in response",
		},
		Payload: map[string]any{"task": "task without id in response"},
	}}

	err := esc.Execute(context.Background(), actions)
	if err != nil {
		t.Fatalf("expected nil error when 202 response omits 'id' field, got: %v", err)
	}
}

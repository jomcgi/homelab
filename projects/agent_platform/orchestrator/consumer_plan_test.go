package main

// consumer_plan_test.go adds unit tests for:
//   - planTracker.Update() and planTracker.Get() — thread-safe container
//   - Consumer.summarizeAndStore() — reads/writes job from store after LLM call
//   - Consumer.summarizeAndStoreOnJob() — mutates job in-place after LLM call

import (
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

// newTestConsumerWithSummarizer creates a Consumer wired to a real Summarizer
// backed by the given httptest.Server. Use this for tests that exercise code
// paths that call c.summarizer.SummarizePlan.
func newTestConsumerWithSummarizer(store Store, srv *httptest.Server) *Consumer {
	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	return NewConsumer(nil, store, &fakeSandbox{}, nil, s, 5*time.Minute, slog.Default())
}

// planSummaryServer returns an httptest.Server that always responds with a
// successful SummarizePlan result: {"title":"<title>","summary":"<summary>"}.
func planSummaryServer(t *testing.T, title, summary string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(chatResponse(`{"title":"` + title + `","summary":"` + summary + `"}`)))
	}))
	t.Cleanup(srv.Close)
	return srv
}

// ---- planTracker unit tests ------------------------------------------------

// TestPlanTracker_GetOnZeroValue verifies that a zero-value planTracker returns
// nil plan and step 0 — no panic, no race.
func TestPlanTracker_GetOnZeroValue(t *testing.T) {
	var p planTracker
	plan, step := p.Get()
	if plan != nil {
		t.Errorf("Get() on zero value: plan = %v, want nil", plan)
	}
	if step != 0 {
		t.Errorf("Get() on zero value: step = %d, want 0", step)
	}
}

// TestPlanTracker_UpdateAndGet verifies that a stored plan and step are
// returned unchanged by a subsequent Get.
func TestPlanTracker_UpdateAndGet(t *testing.T) {
	var p planTracker
	want := []PlanStep{
		{Agent: "researcher", Description: "Investigate", Status: "completed"},
		{Agent: "coder", Description: "Write fix", Status: "running"},
	}
	p.Update(want, 1)

	got, step := p.Get()
	if step != 1 {
		t.Errorf("Get() step = %d, want 1", step)
	}
	if len(got) != len(want) {
		t.Fatalf("Get() plan length = %d, want %d", len(got), len(want))
	}
	for i, s := range want {
		if got[i] != s {
			t.Errorf("plan[%d] = %+v, want %+v", i, got[i], s)
		}
	}
}

// TestPlanTracker_MultipleUpdates verifies that the most recent Update wins.
func TestPlanTracker_MultipleUpdates(t *testing.T) {
	var p planTracker
	p.Update([]PlanStep{{Agent: "a", Description: "first", Status: "completed"}}, 0)
	p.Update([]PlanStep{{Agent: "b", Description: "second", Status: "running"}}, 1)

	got, step := p.Get()
	if step != 1 {
		t.Errorf("step = %d, want 1 (latest update)", step)
	}
	if len(got) != 1 || got[0].Agent != "b" {
		t.Errorf("plan = %+v, want [{Agent:b ...}]", got)
	}
}

// TestPlanTracker_ConcurrentUpdateGet runs concurrent writers and readers to
// confirm there is no data race. Requires -race flag to be meaningful.
func TestPlanTracker_ConcurrentUpdateGet(t *testing.T) {
	var p planTracker
	plan := []PlanStep{{Agent: "a", Description: "step", Status: "running"}}

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(2)
		go func(n int) {
			defer wg.Done()
			p.Update(plan, n)
		}(i)
		go func() {
			defer wg.Done()
			p.Get()
		}()
	}
	wg.Wait()
}

// ---- summarizeAndStore tests -----------------------------------------------

// TestSummarizeAndStore_UpdatesTitleAndSummary verifies the happy path: when
// the LLM returns both title and summary, both are written to the stored job.
func TestSummarizeAndStore_UpdatesTitleAndSummary(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-STORE")
	_ = store.Put(context.Background(), job)

	srv := planSummaryServer(t, "Deploy Service", "Deploys the auth service.")
	c := newTestConsumerWithSummarizer(store, srv)

	plan := []PlanStep{{Agent: "coder", Description: "Write deploy script", Status: "completed"}}
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())

	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Title != "Deploy Service" {
		t.Errorf("Title = %q, want %q", got.Title, "Deploy Service")
	}
	if got.Summary != "Deploys the auth service." {
		t.Errorf("Summary = %q, want %q", got.Summary, "Deploys the auth service.")
	}
}

// TestSummarizeAndStore_OnlyTitleReturned verifies that when the LLM returns
// only a title (empty summary), only Title is updated in the store.
func TestSummarizeAndStore_OnlyTitleReturned(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-TITLE-ONLY")
	_ = store.Put(context.Background(), job)

	srv := planSummaryServer(t, "Fix Bug", "")
	c := newTestConsumerWithSummarizer(store, srv)

	plan := []PlanStep{{Agent: "coder", Description: "Debug", Status: "running"}}
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())

	got, _ := store.Get(context.Background(), job.ID)
	if got.Title != "Fix Bug" {
		t.Errorf("Title = %q, want %q", got.Title, "Fix Bug")
	}
	if got.Summary != "" {
		t.Errorf("Summary = %q, want empty (not returned by LLM)", got.Summary)
	}
}

// TestSummarizeAndStore_OnlySummaryReturned verifies that when the LLM returns
// only a summary (empty title), only Summary is updated in the store.
func TestSummarizeAndStore_OnlySummaryReturned(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-SUMMARY-ONLY")
	_ = store.Put(context.Background(), job)

	srv := planSummaryServer(t, "", "Fixed the auth bug.")
	c := newTestConsumerWithSummarizer(store, srv)

	plan := []PlanStep{{Agent: "coder", Description: "Debug", Status: "running"}}
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())

	got, _ := store.Get(context.Background(), job.ID)
	if got.Summary != "Fixed the auth bug." {
		t.Errorf("Summary = %q, want %q", got.Summary, "Fixed the auth bug.")
	}
	// Title should not have been overwritten with empty string.
	if got.Title != "" {
		t.Errorf("Title = %q, want empty (LLM returned no title)", got.Title)
	}
}

// TestSummarizeAndStore_LLMError_NoStoreUpdate verifies that a summarizer
// error leaves the store unchanged (graceful degradation).
func TestSummarizeAndStore_LLMError_NoStoreUpdate(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-LLM-ERR")
	job.Title = "original title"
	_ = store.Put(context.Background(), job)

	// Server returns 500 → summarizer returns an error.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)

	c := newTestConsumerWithSummarizer(store, srv)
	plan := []PlanStep{{Agent: "a", Description: "step", Status: "running"}}
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())

	got, _ := store.Get(context.Background(), job.ID)
	// Original title must be preserved; summary must remain empty.
	if got.Title != "original title" {
		t.Errorf("Title changed despite LLM error: got %q", got.Title)
	}
}

// TestSummarizeAndStore_EmptyTitleAndSummary_NoStoreUpdate verifies that when
// the LLM returns both empty title and empty summary, the store is not touched.
func TestSummarizeAndStore_EmptyTitleAndSummary_NoStoreUpdate(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-EMPTY")
	job.Title = "keep this"
	_ = store.Put(context.Background(), job)

	srv := planSummaryServer(t, "", "")
	c := newTestConsumerWithSummarizer(store, srv)

	plan := []PlanStep{{Agent: "a", Description: "step", Status: "running"}}
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())

	got, _ := store.Get(context.Background(), job.ID)
	if got.Title != "keep this" {
		t.Errorf("Title should not be overwritten when LLM returns empty; got %q", got.Title)
	}
}

// TestSummarizeAndStore_StoreGetFails_GracefulReturn verifies that if the
// store.Get call inside summarizeAndStore fails, the function returns without
// panicking or crashing.
func TestSummarizeAndStore_StoreGetFails_GracefulReturn(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-SUM-GET-FAIL")
	_ = store.Put(context.Background(), job)

	failStore := &failGetStore{inner: store}
	srv := planSummaryServer(t, "A Title", "A Summary")
	s := NewSummarizer(srv.URL, "test-model", slog.Default())
	c := NewConsumer(nil, failStore, &fakeSandbox{}, nil, s, 5*time.Minute, slog.Default())

	plan := []PlanStep{{Agent: "a", Description: "step", Status: "running"}}
	// Must not panic.
	c.summarizeAndStore(context.Background(), job.ID, job.Task, plan, slog.Default())
}

// ---- summarizeAndStoreOnJob tests ------------------------------------------

// TestSummarizeAndStoreOnJob_UpdatesTitleAndSummary verifies the happy path:
// both title and summary from the LLM are written directly to the job record.
func TestSummarizeAndStoreOnJob_UpdatesTitleAndSummary(t *testing.T) {
	srv := planSummaryServer(t, "Completed Task", "All steps done.")
	c := newTestConsumerWithSummarizer(newMemStore(), srv)

	job := pendingJob("JOB-STOREJ-HAPPY")
	job.Plan = []PlanStep{
		{Agent: "coder", Description: "Write code", Status: "completed"},
	}

	c.summarizeAndStoreOnJob(context.Background(), job, slog.Default())

	if job.Title != "Completed Task" {
		t.Errorf("Title = %q, want %q", job.Title, "Completed Task")
	}
	if job.Summary != "All steps done." {
		t.Errorf("Summary = %q, want %q", job.Summary, "All steps done.")
	}
}

// TestSummarizeAndStoreOnJob_OnlyTitle verifies that an empty summary from the
// LLM does not overwrite an existing summary on the job.
func TestSummarizeAndStoreOnJob_OnlyTitle(t *testing.T) {
	srv := planSummaryServer(t, "New Title", "")
	c := newTestConsumerWithSummarizer(newMemStore(), srv)

	job := pendingJob("JOB-STOREJ-TITLE")
	job.Summary = "existing summary"
	job.Plan = []PlanStep{{Agent: "a", Description: "step", Status: "completed"}}

	c.summarizeAndStoreOnJob(context.Background(), job, slog.Default())

	if job.Title != "New Title" {
		t.Errorf("Title = %q, want %q", job.Title, "New Title")
	}
	// An empty summary from the LLM must not overwrite the existing value.
	if job.Summary != "existing summary" {
		t.Errorf("Summary = %q, want %q (no overwrite)", job.Summary, "existing summary")
	}
}

// TestSummarizeAndStoreOnJob_OnlySummary verifies that an empty title from the
// LLM does not overwrite an existing title on the job.
func TestSummarizeAndStoreOnJob_OnlySummary(t *testing.T) {
	srv := planSummaryServer(t, "", "New summary.")
	c := newTestConsumerWithSummarizer(newMemStore(), srv)

	job := pendingJob("JOB-STOREJ-SUMMARY")
	job.Title = "existing title"
	job.Plan = []PlanStep{{Agent: "a", Description: "step", Status: "completed"}}

	c.summarizeAndStoreOnJob(context.Background(), job, slog.Default())

	if job.Summary != "New summary." {
		t.Errorf("Summary = %q, want %q", job.Summary, "New summary.")
	}
	if job.Title != "existing title" {
		t.Errorf("Title = %q, want %q (no overwrite)", job.Title, "existing title")
	}
}

// TestSummarizeAndStoreOnJob_LLMError_JobUnchanged verifies that when the LLM
// returns an error, the job record is left unchanged.
func TestSummarizeAndStoreOnJob_LLMError_JobUnchanged(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	t.Cleanup(srv.Close)
	c := newTestConsumerWithSummarizer(newMemStore(), srv)

	job := pendingJob("JOB-STOREJ-ERR")
	job.Title = "keep me"
	job.Plan = []PlanStep{{Agent: "a", Description: "step", Status: "running"}}

	c.summarizeAndStoreOnJob(context.Background(), job, slog.Default())

	// Title must not have been cleared by the error path.
	if job.Title != "keep me" {
		t.Errorf("Title = %q after LLM error; want %q", job.Title, "keep me")
	}
	if job.Summary != "" {
		t.Errorf("Summary = %q after LLM error; want empty", job.Summary)
	}
}

// TestSummarizeAndStoreOnJob_ContextCancelled verifies graceful handling when
// the context is already cancelled before the LLM call.
func TestSummarizeAndStoreOnJob_ContextCancelled(t *testing.T) {
	srv := planSummaryServer(t, "A Title", "A Summary")
	c := newTestConsumerWithSummarizer(newMemStore(), srv)

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancelled before call

	job := pendingJob("JOB-STOREJ-CTX")
	job.Plan = []PlanStep{{Agent: "a", Description: "step", Status: "running"}}

	// Must not panic; cancelled context will cause an error in callLLM.
	c.summarizeAndStoreOnJob(ctx, job, slog.Default())
}

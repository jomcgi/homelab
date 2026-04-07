package main

// extra_coverage_test.go fills gaps identified in coverage analysis:
//   1. setupJetStream: stream, KV, and consumer config field assertions
//   2. setupJetStream: consumer error is terminal (not retried)
//   3. Consumer.Run(): context cancellation exits the loop
//   4. Consumer.Run(): fetch error is logged and the loop continues
//   5. Consumer.Run(): a queued job message is dispatched and processed
//   6. syncBuffer: Write with a zero-length slice is a no-op
//   7. pollOutput: X-Output-Offset header is forwarded across subsequent calls
//   8. pollUntilDone: cancelFn returning true aborts the polling loop
//   9. Summarizer.callLLM: request construction failure (malformed URL)

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// ============================================================
// 1 & 2. setupJetStream config field assertions
// ============================================================

// configCapturingJS implements jetStreamSetup and captures the configs
// passed to each Create call so tests can assert on specific field values.
type configCapturingJS struct {
	streamCfg   jetstream.StreamConfig
	kvCfg       jetstream.KeyValueConfig
	consumerCfg jetstream.ConsumerConfig
}

func (c *configCapturingJS) CreateOrUpdateStream(_ context.Context, cfg jetstream.StreamConfig) (jetstream.Stream, error) {
	c.streamCfg = cfg
	return nil, nil
}

func (c *configCapturingJS) CreateOrUpdateKeyValue(_ context.Context, cfg jetstream.KeyValueConfig) (jetstream.KeyValue, error) {
	c.kvCfg = cfg
	return &fakeKV{}, nil
}

func (c *configCapturingJS) CreateOrUpdateConsumer(_ context.Context, _ string, cfg jetstream.ConsumerConfig) (jetstream.Consumer, error) {
	c.consumerCfg = cfg
	return &fakeConsumer{}, nil
}

// TestSetupJetStream_StreamConfigValues verifies that setupJetStream passes the
// correct field values for the JetStream stream configuration.
// A misconfigured stream (wrong Subjects, Retention, or MaxMsgs) would silently
// misbehave in production — this test makes the contract explicit.
func TestSetupJetStream_StreamConfigValues(t *testing.T) {
	cap := &configCapturingJS{}
	_, _, err := setupJetStream(context.Background(), cap, 5, slog.Default())
	if err != nil {
		t.Fatalf("setupJetStream: %v", err)
	}
	if cap.streamCfg.Name != streamName {
		t.Errorf("stream Name = %q, want %q", cap.streamCfg.Name, streamName)
	}
	if len(cap.streamCfg.Subjects) != 1 || cap.streamCfg.Subjects[0] != subject {
		t.Errorf("stream Subjects = %v, want [%q]", cap.streamCfg.Subjects, subject)
	}
	if cap.streamCfg.Retention != jetstream.WorkQueuePolicy {
		t.Errorf("stream Retention = %v, want WorkQueuePolicy", cap.streamCfg.Retention)
	}
	if cap.streamCfg.MaxMsgs != 1000 {
		t.Errorf("stream MaxMsgs = %d, want 1000", cap.streamCfg.MaxMsgs)
	}
}

// TestSetupJetStream_KVConfigValues verifies the KeyValue bucket configuration.
func TestSetupJetStream_KVConfigValues(t *testing.T) {
	cap := &configCapturingJS{}
	_, _, err := setupJetStream(context.Background(), cap, 5, slog.Default())
	if err != nil {
		t.Fatalf("setupJetStream: %v", err)
	}
	if cap.kvCfg.Bucket != kvBucket {
		t.Errorf("KV Bucket = %q, want %q", cap.kvCfg.Bucket, kvBucket)
	}
	wantTTL := 7 * 24 * time.Hour
	if cap.kvCfg.TTL != wantTTL {
		t.Errorf("KV TTL = %v, want %v", cap.kvCfg.TTL, wantTTL)
	}
}

// TestSetupJetStream_ConsumerConfigValues verifies the consumer configuration,
// including that MaxAckPending is set to the maxConcurrent argument.
func TestSetupJetStream_ConsumerConfigValues(t *testing.T) {
	const maxConcurrent = 7
	cap := &configCapturingJS{}
	_, _, err := setupJetStream(context.Background(), cap, maxConcurrent, slog.Default())
	if err != nil {
		t.Fatalf("setupJetStream: %v", err)
	}
	if cap.consumerCfg.Name != "orchestrator" {
		t.Errorf("consumer Name = %q, want %q", cap.consumerCfg.Name, "orchestrator")
	}
	if cap.consumerCfg.Durable != "orchestrator" {
		t.Errorf("consumer Durable = %q, want %q", cap.consumerCfg.Durable, "orchestrator")
	}
	if cap.consumerCfg.AckPolicy != jetstream.AckExplicitPolicy {
		t.Errorf("consumer AckPolicy = %v, want AckExplicitPolicy", cap.consumerCfg.AckPolicy)
	}
	if cap.consumerCfg.MaxAckPending != maxConcurrent {
		t.Errorf("consumer MaxAckPending = %d, want %d", cap.consumerCfg.MaxAckPending, maxConcurrent)
	}
	wantAckWait := 2 * time.Minute
	if cap.consumerCfg.AckWait != wantAckWait {
		t.Errorf("consumer AckWait = %v, want %v", cap.consumerCfg.AckWait, wantAckWait)
	}
}

// TestSetupJetStream_ConsumerFailureIsTerminal verifies that a consumer
// creation error does not trigger the stream retry loop — it is treated as a
// terminal, non-retryable error. (Contrast with stream errors, which do retry.)
func TestSetupJetStream_ConsumerFailureIsTerminal(t *testing.T) {
	fake := &fakeJetStreamSetup{consumerErr: errors.New("consumer broken")}
	_, _, err := setupJetStream(context.Background(), fake, 3, slog.Default())
	if err == nil {
		t.Fatal("expected error when consumer creation fails")
	}
	// Consumer failure must not trigger the stream retry loop.
	if got := fake.streamCalls.Load(); got != 1 {
		t.Fatalf("expected 1 stream call (no retry after consumer failure), got %d", got)
	}
}

// ============================================================
// 3–5. Consumer.Run() outer fetch loop tests
// ============================================================

// runnableFakeConsumer is a fake jetstream.Consumer whose Fetch method
// delegates to a user-supplied function. All other methods are inherited from
// the embedded no-op stub and will panic if unexpectedly called.
type runnableFakeConsumer struct {
	jetstream.Consumer
	fetchFn func(batch int, opts ...jetstream.FetchOpt) (jetstream.MessageBatch, error)
}

func (f *runnableFakeConsumer) Fetch(batch int, opts ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
	return f.fetchFn(batch, opts...)
}

// fakeMsgBatch implements jetstream.MessageBatch for testing.
// It delivers a pre-seeded slice of messages through Messages() and returns
// a fixed error (or nil) from Error().
type fakeMsgBatch struct {
	msgs []jetstream.Msg
	err  error
}

func (b *fakeMsgBatch) Messages() <-chan jetstream.Msg {
	ch := make(chan jetstream.Msg, len(b.msgs))
	for _, m := range b.msgs {
		ch <- m
	}
	close(ch)
	return ch
}

func (b *fakeMsgBatch) Error() error { return b.err }

// TestConsumerRun_ExitsOnContextCancel verifies that Consumer.Run exits cleanly
// when its context is cancelled, even while a Fetch call is in progress.
func TestConsumerRun_ExitsOnContextCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	fetchCalled := make(chan struct{}, 1)
	cons := &runnableFakeConsumer{
		fetchFn: func(_ int, _ ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
			select {
			case fetchCalled <- struct{}{}:
			default:
			}
			// Block until context is cancelled, then surface the error so
			// Run() can observe ctx.Err() != nil and exit the loop.
			<-ctx.Done()
			return nil, ctx.Err()
		},
	}

	c := NewConsumer(cons, newMemStore(), &fakeSandbox{}, nil, nil, 5*time.Minute, slog.Default())
	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Run(ctx)
	}()

	// Wait for the first Fetch call to confirm Run() has started.
	select {
	case <-fetchCalled:
	case <-time.After(2 * time.Second):
		cancel()
		t.Fatal("expected Fetch to be called within 2s")
	}

	cancel()

	select {
	case <-done:
		// Pass — Run() exited cleanly.
	case <-time.After(3 * time.Second):
		t.Fatal("Consumer.Run did not exit within 3s after context cancellation")
	}
}

// TestConsumerRun_ContinuesAfterFetchError verifies that a transient Fetch error
// (with a live context) causes Run to log the error and loop — it must NOT exit.
// The test injects one error then cancels the context on the second Fetch call.
func TestConsumerRun_ContinuesAfterFetchError(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	fetchCount := 0
	cons := &runnableFakeConsumer{
		fetchFn: func(_ int, _ ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
			fetchCount++
			if fetchCount == 1 {
				// First call: inject a transient, non-context error.
				return nil, errors.New("transient NATS fetch failure")
			}
			// Second call: block until context is cancelled (proving the loop
			// continued after the first error).
			<-ctx.Done()
			return nil, ctx.Err()
		},
	}

	c := NewConsumer(cons, newMemStore(), &fakeSandbox{}, nil, nil, 5*time.Minute, slog.Default())
	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Run(ctx)
	}()

	// Allow the loop to process the first error and reach the second Fetch.
	time.Sleep(100 * time.Millisecond)
	cancel()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("Consumer.Run did not exit within 3s")
	}

	// Verify the loop continued after the first error (at least 2 Fetch calls).
	if fetchCount < 2 {
		t.Errorf("expected ≥2 Fetch calls (continue after error), got %d", fetchCount)
	}
}

// TestConsumerRun_DispatchesJobMessage verifies that Consumer.Run processes a
// NATS message end-to-end: fetches it, dispatches to processJob, and writes
// the final SUCCEEDED status back to the store before exiting.
func TestConsumerRun_DispatchesJobMessage(t *testing.T) {
	store := newMemStore()
	job := pendingJob("JOB-RUN-DISPATCH")
	_ = store.Put(context.Background(), job)

	ctx, cancel := context.WithCancel(context.Background())

	// sandboxCalled is closed when the sandbox Run method is invoked, signalling
	// that processJob has started executing the job.
	sandboxCalled := make(chan struct{})
	sandbox := &fakeSandbox{
		runFn: func(_ context.Context, _, _, _ string, _ func() bool, _ *syncBuffer, _ *planTracker) (*ExecResult, error) {
			close(sandboxCalled)
			return &ExecResult{ExitCode: 0, Output: "dispatched"}, nil
		},
	}

	msgDelivered := false
	cons := &runnableFakeConsumer{
		fetchFn: func(_ int, _ ...jetstream.FetchOpt) (jetstream.MessageBatch, error) {
			if !msgDelivered {
				msgDelivered = true
				return &fakeMsgBatch{msgs: []jetstream.Msg{newFakeMsg([]byte(job.ID))}}, nil
			}
			// All subsequent Fetches block until context is cancelled.
			<-ctx.Done()
			return nil, ctx.Err()
		},
	}

	c := NewConsumer(cons, store, sandbox, nil, nil, 5*time.Minute, slog.Default())
	runDone := make(chan struct{})
	go func() {
		defer close(runDone)
		c.Run(ctx)
	}()

	// Wait for the sandbox to be invoked, confirming message dispatch worked.
	select {
	case <-sandboxCalled:
	case <-time.After(5 * time.Second):
		cancel()
		t.Fatal("sandbox was not called within 5s")
	}

	// Cancel to let Run() exit. wg.Wait() inside Run() ensures the in-flight
	// goroutine (processJob) completes before Run() returns.
	cancel()

	select {
	case <-runDone:
	case <-time.After(5 * time.Second):
		t.Fatal("Consumer.Run did not exit within 5s after cancel")
	}

	// After runDone the job goroutine has fully completed — check final state.
	got, err := store.Get(context.Background(), job.ID)
	if err != nil {
		t.Fatalf("store.Get: %v", err)
	}
	if got.Status != JobSucceeded {
		t.Errorf("job status = %s, want SUCCEEDED", got.Status)
	}
}

// ============================================================
// 6. syncBuffer: Write with a zero-length slice
// ============================================================

// TestSyncBuffer_ZeroLengthWrite verifies that writing an empty slice to a
// syncBuffer is a no-op: no error is returned, no bytes are added, and the
// buffer's contents are unchanged.
func TestSyncBuffer_ZeroLengthWrite(t *testing.T) {
	buf := newSyncBuffer(1024)

	n, err := buf.Write([]byte{})
	if err != nil {
		t.Errorf("Write(empty) returned error: %v", err)
	}
	if n != 0 {
		t.Errorf("Write(empty) returned n=%d, want 0", n)
	}
	if buf.Len() != 0 {
		t.Errorf("Len after empty write = %d, want 0", buf.Len())
	}
	if buf.String() != "" {
		t.Errorf("String after empty write = %q, want empty", buf.String())
	}
}

// TestSyncBuffer_ZeroLengthWriteAfterData verifies that writing an empty slice
// to a non-empty buffer does not alter its existing contents.
func TestSyncBuffer_ZeroLengthWriteAfterData(t *testing.T) {
	buf := newSyncBuffer(0)
	buf.Write([]byte("hello"))

	if _, err := buf.Write([]byte{}); err != nil {
		t.Errorf("Write(empty) after data returned error: %v", err)
	}
	if buf.String() != "hello" {
		t.Errorf("String after empty write = %q, want %q", buf.String(), "hello")
	}
	if buf.Len() != 5 {
		t.Errorf("Len after empty write = %d, want 5", buf.Len())
	}
}

// ============================================================
// 7. pollOutput: offset header is forwarded across subsequent calls
// ============================================================

// TestPollOutput_OffsetAdvancesAcrossMultipleCalls verifies the full
// offset-chaining contract: the offset returned by pollOutput call N is
// used as the query parameter in call N+1. This is the mechanism that prevents
// the runner from re-delivering already-seen output chunks.
func TestPollOutput_OffsetAdvancesAcrossMultipleCalls(t *testing.T) {
	var receivedOffsets []string
	callNum := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callNum++
		receivedOffsets = append(receivedOffsets, r.URL.Query().Get("offset"))
		// Return deterministic new offsets: 17, 34, …
		w.Header().Set("X-Output-Offset", strconv.Itoa(callNum*17))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("chunk"))
	}))
	defer srv.Close()

	s := newTestSandbox()
	buf := newSyncBuffer(0)

	// First call: start at offset 0, server acknowledges offset=17.
	off1, err := s.pollOutput(context.Background(), srv.URL, 0, buf)
	if err != nil {
		t.Fatalf("first pollOutput: %v", err)
	}

	// Second call: caller passes off1 (=17); server acknowledges offset=34.
	off2, err := s.pollOutput(context.Background(), srv.URL, off1, buf)
	if err != nil {
		t.Fatalf("second pollOutput: %v", err)
	}

	if len(receivedOffsets) != 2 {
		t.Fatalf("expected 2 server requests, got %d", len(receivedOffsets))
	}
	if receivedOffsets[0] != "0" {
		t.Errorf("first request offset param = %q, want %q", receivedOffsets[0], "0")
	}
	if receivedOffsets[1] != "17" {
		t.Errorf("second request offset param = %q, want %q", receivedOffsets[1], "17")
	}
	if off1 != 17 {
		t.Errorf("offset after first poll = %d, want 17", off1)
	}
	if off2 != 34 {
		t.Errorf("offset after second poll = %d, want 34", off2)
	}
	if buf.String() != "chunkchunk" {
		t.Errorf("accumulated buffer = %q, want %q", buf.String(), "chunkchunk")
	}
}

// ============================================================
// 8. pollUntilDone: cancelFn returning true aborts the polling loop
// ============================================================

// TestPollUntilDone_CancelFnAbortsDuringLoop verifies that pollUntilDone
// returns a "cancelled" error when cancelFn returns true after the initial
// poll fires.
//
// Note: pollUntilDone has a hardcoded 5-second initial timer before the first
// poll, so this test takes approximately 5–6 seconds.
func TestPollUntilDone_CancelFnAbortsDuringLoop(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/output" {
			w.WriteHeader(http.StatusOK)
			return
		}
		// /status: always running, never completes.
		json.NewEncoder(w).Encode(map[string]any{"state": "running"})
	}))
	defer srv.Close()

	s := newTestSandbox()

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	buf := newSyncBuffer(maxOutputBytes)
	_, err := s.pollUntilDone(ctx, srv.URL, "test-claim",
		func() bool { return true }, // always cancelled
		buf, &planTracker{})

	if err == nil {
		t.Fatal("expected error when cancelFn returns true, got nil")
	}
	if !strings.Contains(err.Error(), "cancelled") {
		t.Errorf("expected 'cancelled' in error message, got: %v", err)
	}
}

// ============================================================
// 9. Summarizer.callLLM: request construction failure (malformed URL)
// ============================================================

// TestSummarizeTask_MalformedURL verifies that a null byte in the inference URL
// causes callLLM to return a "create request" error rather than panicking or
// silently succeeding. A null byte causes url.Parse (invoked by
// http.NewRequestWithContext) to reject the URL.
func TestSummarizeTask_MalformedURL(t *testing.T) {
	summarizer := NewSummarizer("http://\x00invalid", "test-model", slog.Default())
	_, err := summarizer.SummarizeTask(context.Background(), "test task")
	if err == nil {
		t.Fatal("expected error for malformed URL in SummarizeTask, got nil")
	}
}

// TestSummarizePlan_MalformedURL verifies that SummarizePlan also propagates
// the request construction error from callLLM when the URL is malformed.
func TestSummarizePlan_MalformedURL(t *testing.T) {
	summarizer := NewSummarizer("http://\x00invalid", "test-model", slog.Default())
	plan := []PlanStep{{Agent: "agent", Description: "do work", Status: "running"}}
	_, _, err := summarizer.SummarizePlan(context.Background(), "test task", plan)
	if err == nil {
		t.Fatal("expected error for malformed URL in SummarizePlan, got nil")
	}
}

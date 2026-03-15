package main

import (
	"context"
	"errors"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// fakeJetStreamSetup implements jetStreamSetup for testing.
type fakeJetStreamSetup struct {
	streamFailures int32 // number of times CreateOrUpdateStream should fail
	streamCalls    atomic.Int32
	kvErr          error
	consumerErr    error
}

func (f *fakeJetStreamSetup) CreateOrUpdateStream(_ context.Context, _ jetstream.StreamConfig) (jetstream.Stream, error) {
	n := f.streamCalls.Add(1)
	if n <= f.streamFailures {
		return nil, context.DeadlineExceeded
	}
	return nil, nil
}

func (f *fakeJetStreamSetup) CreateOrUpdateKeyValue(_ context.Context, _ jetstream.KeyValueConfig) (jetstream.KeyValue, error) {
	if f.kvErr != nil {
		return nil, f.kvErr
	}
	return &fakeKV{}, nil
}

func (f *fakeJetStreamSetup) CreateOrUpdateConsumer(_ context.Context, _ string, _ jetstream.ConsumerConfig) (jetstream.Consumer, error) {
	if f.consumerErr != nil {
		return nil, f.consumerErr
	}
	return &fakeConsumer{}, nil
}

func TestSetupJetStream_SucceedsImmediately(t *testing.T) {
	fake := &fakeJetStreamSetup{}
	logger := slog.Default()

	kv, cons, err := setupJetStream(context.Background(), fake, 3, logger)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if kv == nil || cons == nil {
		t.Fatal("expected non-nil kv and consumer")
	}
	if got := fake.streamCalls.Load(); got != 1 {
		t.Fatalf("expected 1 stream call, got %d", got)
	}
}

func TestSetupJetStream_RetriesOnTransientFailure(t *testing.T) {
	fake := &fakeJetStreamSetup{streamFailures: 3}
	logger := slog.Default()

	kv, cons, err := setupJetStream(context.Background(), fake, 3, logger)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if kv == nil || cons == nil {
		t.Fatal("expected non-nil kv and consumer")
	}
	if got := fake.streamCalls.Load(); got != 4 {
		t.Fatalf("expected 4 stream calls (3 failures + 1 success), got %d", got)
	}
}

func TestSetupJetStream_RespectsContextCancellation(t *testing.T) {
	fake := &fakeJetStreamSetup{streamFailures: 100}
	logger := slog.Default()

	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	_, _, err := setupJetStream(ctx, fake, 3, logger)
	if !errors.Is(err, context.DeadlineExceeded) && !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context error, got: %v", err)
	}
}

func TestSetupJetStream_KVFailureIsTerminal(t *testing.T) {
	fake := &fakeJetStreamSetup{kvErr: errors.New("kv broken")}
	logger := slog.Default()

	_, _, err := setupJetStream(context.Background(), fake, 3, logger)
	if err == nil {
		t.Fatal("expected error")
	}
	if got := fake.streamCalls.Load(); got != 1 {
		t.Fatalf("expected 1 stream call (no retry after KV failure), got %d", got)
	}
}

// fakeKV satisfies jetstream.KeyValue with minimal stubs.
type fakeKV struct{ jetstream.KeyValue }

// fakeConsumer satisfies jetstream.Consumer with minimal stubs.
type fakeConsumer struct{ jetstream.Consumer }

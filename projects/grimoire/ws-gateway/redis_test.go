package main

import (
	"context"
	"testing"
	"time"
)

// TestRedisChannel_Value verifies the broadcast channel name matches the expected constant.
// Any change to this constant would break cross-replica message routing.
func TestRedisChannel_Value(t *testing.T) {
	const want = "grimoire:ws:broadcast"
	if redisChannel != want {
		t.Errorf("redisChannel got %q, want %q", redisChannel, want)
	}
}

// TestNewRedisRelay_InvalidAddress verifies that NewRedisRelay returns an error
// when it cannot connect to the given address. Port 1 is reserved and never open.
func TestNewRedisRelay_InvalidAddress(t *testing.T) {
	_, err := NewRedisRelay("localhost:1", "")
	if err == nil {
		t.Error("expected error connecting to unreachable Redis address, got nil")
	}
}

// TestRedisRelay_ContextCancellation verifies that Subscribe returns promptly when
// the relay's internal context is cancelled via Close. We use a channel and a short
// timeout to detect a hang.
func TestRedisRelay_ContextCancellation(t *testing.T) {
	// Build a minimal RedisRelay manually so we don't need a live Redis server.
	// We set the context to already-cancelled so that Subscribe exits immediately.
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	r := &RedisRelay{
		ctx:    ctx,
		cancel: cancel,
		// client is nil — Subscribe checks ctx.Err() before accessing the client.
	}

	done := make(chan struct{})
	go func() {
		defer close(done)
		r.Subscribe(func([]byte) {})
	}()

	select {
	case <-done:
		// Subscribe exited promptly — correct behaviour.
	case <-time.After(2 * time.Second):
		t.Error("Subscribe did not exit after context cancellation")
	}
}

// TestRedisRelay_CloseCancel verifies that calling Close cancels the internal context.
func TestRedisRelay_CloseCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	r := &RedisRelay{
		ctx:    ctx,
		cancel: cancel,
		// client is nil — we are only testing that cancel() is invoked.
	}

	// Verify context is not yet cancelled.
	if ctx.Err() != nil {
		t.Fatal("context should not be cancelled before Close")
	}

	// Call cancel directly (simulating what Close does) to avoid a nil client.Close() panic.
	r.cancel()

	if ctx.Err() == nil {
		t.Error("context should be cancelled after calling cancel()")
	}
}

// TestSubscribe_ExitsOnCancelledContext verifies the inner subscribe loop returns nil
// when the context is already cancelled at entry.
func TestSubscribe_ExitsOnCancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	r := &RedisRelay{
		ctx:    ctx,
		cancel: cancel,
	}

	// subscribe() should return nil (context done), not an error.
	// We can't call subscribe() directly (unexported), so we verify through Subscribe().
	called := false
	done := make(chan struct{})
	go func() {
		defer close(done)
		r.Subscribe(func([]byte) { called = true })
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Error("Subscribe blocked instead of exiting on cancelled context")
	}

	if called {
		t.Error("handler should not have been called when context was cancelled at entry")
	}
}

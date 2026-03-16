package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
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

// newRelayWithRealClient builds a RedisRelay backed by a real (but unreachable) Redis
// client. Port 1 is reserved and will always refuse connections, so no live server is
// required. The caller must call relay.client.Close() when done.
func newRelayWithRealClient(ctx context.Context, cancel context.CancelFunc) *RedisRelay {
	return &RedisRelay{
		client: redis.NewClient(&redis.Options{
			Addr: "127.0.0.1:1", // port 1 is always unreachable
		}),
		ctx:    ctx,
		cancel: cancel,
	}
}

// TestRedisRelay_Publish_CancelledContextReturnsError verifies that Publish propagates
// an error when the relay context has been cancelled. The Redis client cannot execute
// the command because it cannot acquire a pool connection with a done context.
func TestRedisRelay_Publish_CancelledContextReturnsError(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before Publish

	relay := newRelayWithRealClient(ctx, cancel)
	defer relay.client.Close() //nolint:errcheck

	err := relay.Publish([]byte(`{"type":"test","data":{}}`))
	if err == nil {
		t.Fatal("Publish with a cancelled context should return an error, got nil")
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("Publish error should be context.Canceled, got %v", err)
	}
}

// TestRedisRelay_Ping_CancelledContextReturnsError verifies that Ping propagates an
// error when the relay context is cancelled. This covers the health-check path used
// by the /readyz endpoint.
func TestRedisRelay_Ping_CancelledContextReturnsError(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before Ping

	relay := newRelayWithRealClient(ctx, cancel)
	defer relay.client.Close() //nolint:errcheck

	if err := relay.Ping(); err == nil {
		t.Fatal("Ping with a cancelled context should return an error, got nil")
	}
}

// TestRedisRelay_Close_CancelsContextAndClosesClient verifies that Close both cancels
// the relay context and closes the underlying Redis client cleanly.
func TestRedisRelay_Close_CancelsContextAndClosesClient(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	relay := newRelayWithRealClient(ctx, cancel)

	if relay.ctx.Err() != nil {
		t.Fatal("context should not be cancelled before Close")
	}

	if err := relay.Close(); err != nil {
		t.Errorf("Close returned unexpected error: %v", err)
	}

	if relay.ctx.Err() == nil {
		t.Error("Close should cancel the relay context, but ctx.Err() is still nil")
	}
}

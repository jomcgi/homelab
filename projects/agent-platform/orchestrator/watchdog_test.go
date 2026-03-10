package main

import (
	"testing"
)

func TestSyncBuffer_ConcurrentAccess(t *testing.T) {
	buf := newSyncBuffer(0) // uncapped for this test
	done := make(chan struct{})

	// Writer goroutine.
	go func() {
		for i := 0; i < 100; i++ {
			buf.Write([]byte("x"))
		}
		close(done)
	}()

	// Reader goroutine (concurrent).
	for i := 0; i < 50; i++ {
		_ = buf.String()
		_ = buf.Len()
	}

	<-done
	if buf.Len() != 100 {
		t.Fatalf("expected length 100, got %d", buf.Len())
	}
}

func TestSyncBuffer_CapsMemory(t *testing.T) {
	buf := newSyncBuffer(100)

	// Write 250 bytes — should trigger truncation at 200 (2*maxRetain).
	for i := 0; i < 250; i++ {
		buf.Write([]byte("x"))
	}

	// Buffer should have been truncated to maxRetain (100 bytes).
	if buf.Len() > 200 {
		t.Fatalf("expected buffer to be capped, got %d bytes", buf.Len())
	}
}

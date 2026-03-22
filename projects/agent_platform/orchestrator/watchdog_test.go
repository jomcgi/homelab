package main

import (
	"strings"
	"testing"
)

// ---- syncBuffer single-threaded unit tests ----------------------------------

func TestSyncBuffer_String_Empty(t *testing.T) {
	buf := newSyncBuffer(0)
	if got := buf.String(); got != "" {
		t.Errorf("String() on empty buffer = %q, want %q", got, "")
	}
}

func TestSyncBuffer_String_AfterWrite(t *testing.T) {
	buf := newSyncBuffer(0)
	buf.Write([]byte("hello"))
	if got := buf.String(); got != "hello" {
		t.Errorf("String() = %q, want %q", got, "hello")
	}
}

func TestSyncBuffer_Len_Empty(t *testing.T) {
	buf := newSyncBuffer(0)
	if got := buf.Len(); got != 0 {
		t.Errorf("Len() on empty buffer = %d, want 0", got)
	}
}

func TestSyncBuffer_Len_AfterWrite(t *testing.T) {
	buf := newSyncBuffer(0)
	data := []byte("hello world")
	buf.Write(data)
	if got := buf.Len(); got != len(data) {
		t.Errorf("Len() = %d, want %d", got, len(data))
	}
}

func TestSyncBuffer_Write_ReturnsBytesWritten(t *testing.T) {
	buf := newSyncBuffer(0)
	data := []byte("test data")
	n, err := buf.Write(data)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if n != len(data) {
		t.Errorf("Write() n = %d, want %d", n, len(data))
	}
}

// TestSyncBuffer_Write_ExactlyAtLimit verifies that writing exactly 2*maxRetain
// bytes does NOT trigger truncation (truncation only fires when buf.Len() is
// strictly greater than 2*maxRetain after the write).
func TestSyncBuffer_Write_ExactlyAtLimit(t *testing.T) {
	maxRetain := 10
	buf := newSyncBuffer(maxRetain)

	// Write exactly 2*maxRetain bytes in one shot.
	data := []byte(strings.Repeat("x", 2*maxRetain))
	buf.Write(data)

	// Buffer should hold all bytes — not truncated because len == 2*maxRetain,
	// not strictly greater.
	if got := buf.Len(); got != 2*maxRetain {
		t.Errorf("Len() at exact limit = %d, want %d (no truncation)", got, 2*maxRetain)
	}
}

// TestSyncBuffer_Write_JustOverLimit verifies that writing one byte beyond
// 2*maxRetain triggers truncation down to maxRetain bytes.
func TestSyncBuffer_Write_JustOverLimit(t *testing.T) {
	maxRetain := 10
	buf := newSyncBuffer(maxRetain)

	// Write 2*maxRetain+1 bytes to trigger truncation.
	data := []byte(strings.Repeat("y", 2*maxRetain+1))
	buf.Write(data)

	// After truncation the buffer should hold exactly maxRetain bytes.
	if got := buf.Len(); got != maxRetain {
		t.Errorf("Len() after truncation = %d, want %d", got, maxRetain)
	}
}

// TestSyncBuffer_Write_TruncationKeepsTail verifies that after truncation the
// buffer holds the *tail* of the data (the most recent bytes), not the head.
func TestSyncBuffer_Write_TruncationKeepsTail(t *testing.T) {
	maxRetain := 5
	buf := newSyncBuffer(maxRetain)

	// Write 2*maxRetain+1 bytes with distinguishable head and tail.
	head := strings.Repeat("a", 2*maxRetain) // "aaaaaaaaaa"
	tail := "BBBBB"                           // last 5 bytes
	buf.Write([]byte(head + tail))

	got := buf.String()
	if got != tail {
		t.Errorf("String() after truncation = %q, want tail %q", got, tail)
	}
}

// TestSyncBuffer_Write_NoCapZero verifies that maxRetain=0 disables truncation
// entirely, allowing the buffer to grow without bound.
func TestSyncBuffer_Write_NoCapZero(t *testing.T) {
	buf := newSyncBuffer(0) // cap disabled

	// Write a large amount — should never truncate.
	large := strings.Repeat("z", 10000)
	buf.Write([]byte(large))

	if got := buf.Len(); got != 10000 {
		t.Errorf("Len() with maxRetain=0 = %d, want 10000 (no truncation)", got)
	}
}

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

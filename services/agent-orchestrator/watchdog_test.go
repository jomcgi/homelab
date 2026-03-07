package main

import (
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestActivityWatchdog_TriggersOnInactivity(t *testing.T) {
	var triggered atomic.Bool
	w := newActivityWatchdog(50*time.Millisecond, func() {
		triggered.Store(true)
	})
	defer w.Stop()

	time.Sleep(100 * time.Millisecond)
	if !triggered.Load() {
		t.Fatal("expected watchdog to trigger after inactivity")
	}
}

func TestActivityWatchdog_ResetsOnWrite(t *testing.T) {
	var triggered atomic.Bool
	w := newActivityWatchdog(80*time.Millisecond, func() {
		triggered.Store(true)
	})
	defer w.Stop()

	// Write before threshold to keep resetting.
	for i := 0; i < 5; i++ {
		time.Sleep(30 * time.Millisecond)
		w.Write([]byte("ping"))
	}

	if triggered.Load() {
		t.Fatal("expected watchdog NOT to trigger while receiving writes")
	}
}

func TestActivityWatchdog_StopPreventsCallback(t *testing.T) {
	var triggered atomic.Bool
	w := newActivityWatchdog(50*time.Millisecond, func() {
		triggered.Store(true)
	})
	w.Stop()

	time.Sleep(100 * time.Millisecond)
	if triggered.Load() {
		t.Fatal("expected watchdog NOT to trigger after Stop()")
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

func TestBuildTaskPrompt_FirstAttempt(t *testing.T) {
	c := &Consumer{}
	job := &JobRecord{Task: "run tests"}
	result := c.buildTaskPrompt(job, 1)
	if result != "run tests" {
		t.Fatalf("expected raw task, got %q", result)
	}
}

func TestBuildTaskPrompt_RetryWithContext(t *testing.T) {
	c := &Consumer{}
	exitCode := 1
	job := &JobRecord{
		Task: "run tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: "error: test failed"},
			{Number: 2},
		},
	}
	result := c.buildTaskPrompt(job, 2)

	if !strings.Contains(result, "retry attempt 2") {
		t.Fatal("expected retry context in prompt")
	}
	if !strings.Contains(result, "exit code 1") {
		t.Fatal("expected previous exit code in prompt")
	}
	if !strings.Contains(result, "error: test failed") {
		t.Fatal("expected previous output in prompt")
	}
	if !strings.Contains(result, "run tests") {
		t.Fatal("expected original task in prompt")
	}
}

func TestBuildTaskPrompt_TruncatesLongOutput(t *testing.T) {
	c := &Consumer{}
	exitCode := 1
	longOutput := strings.Repeat("a", 3000)
	job := &JobRecord{
		Task: "run tests",
		Attempts: []Attempt{
			{Number: 1, ExitCode: &exitCode, Output: longOutput},
			{Number: 2},
		},
	}
	result := c.buildTaskPrompt(job, 2)

	// The prompt should contain at most 2000 chars of previous output.
	if strings.Contains(result, strings.Repeat("a", 2001)) {
		t.Fatal("expected output to be truncated to 2000 chars")
	}
}

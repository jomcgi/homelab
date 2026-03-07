package main

import (
	"bytes"
	"sync"
	"time"
)

// activityWatchdog monitors output activity and triggers a timeout
// if no writes occur within the configured threshold.
type activityWatchdog struct {
	mu        sync.Mutex
	timer     *time.Timer
	threshold time.Duration
	onTimeout func()
	stopped   bool
}

func newActivityWatchdog(threshold time.Duration, onTimeout func()) *activityWatchdog {
	w := &activityWatchdog{
		threshold: threshold,
		onTimeout: onTimeout,
	}
	w.timer = time.AfterFunc(threshold, func() {
		w.mu.Lock()
		defer w.mu.Unlock()
		if !w.stopped {
			w.onTimeout()
		}
	})
	return w
}

func (w *activityWatchdog) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if !w.stopped {
		w.timer.Reset(w.threshold)
	}
	return len(p), nil
}

func (w *activityWatchdog) Stop() {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.stopped = true
	w.timer.Stop()
}

// syncBuffer is a thread-safe buffer for concurrent read/write access.
type syncBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *syncBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *syncBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

func (b *syncBuffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Len()
}

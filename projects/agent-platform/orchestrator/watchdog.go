package main

import (
	"bytes"
	"sync"
)

// syncBuffer is a thread-safe buffer for concurrent read/write access.
// It caps memory usage by truncating to the last maxRetain bytes when
// the buffer exceeds 2*maxRetain, keeping only the tail we need.
type syncBuffer struct {
	mu        sync.Mutex
	buf       bytes.Buffer
	maxRetain int
}

func newSyncBuffer(maxRetain int) *syncBuffer {
	return &syncBuffer{maxRetain: maxRetain}
}

func (b *syncBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	n, err := b.buf.Write(p)
	if b.maxRetain > 0 && b.buf.Len() > 2*b.maxRetain {
		tail := b.buf.Bytes()[b.buf.Len()-b.maxRetain:]
		b.buf.Reset()
		b.buf.Write(tail)
	}
	return n, err
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

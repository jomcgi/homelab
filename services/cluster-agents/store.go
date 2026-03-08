package main

import (
	"context"
	"sync"
	"time"
)

// FindingsStore tracks escalated findings for deduplication.
type FindingsStore interface {
	ShouldEscalate(ctx context.Context, fingerprint string) (bool, error)
	MarkEscalated(ctx context.Context, fingerprint string, ttl time.Duration) error
	MarkResolved(ctx context.Context, fingerprint string) error
}

type findingEntry struct {
	ExpiresAt time.Time
}

// MemFindingsStore is an in-memory implementation for testing and single-instance use.
type MemFindingsStore struct {
	mu      sync.Mutex
	entries map[string]findingEntry
}

func NewMemFindingsStore() *MemFindingsStore {
	return &MemFindingsStore{entries: make(map[string]findingEntry)}
}

func (s *MemFindingsStore) ShouldEscalate(_ context.Context, fingerprint string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, exists := s.entries[fingerprint]
	if !exists {
		return true, nil
	}
	if time.Now().After(entry.ExpiresAt) {
		delete(s.entries, fingerprint)
		return true, nil
	}
	return false, nil
}

func (s *MemFindingsStore) MarkEscalated(_ context.Context, fingerprint string, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.entries[fingerprint] = findingEntry{ExpiresAt: time.Now().Add(ttl)}
	return nil
}

func (s *MemFindingsStore) MarkResolved(_ context.Context, fingerprint string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.entries, fingerprint)
	return nil
}

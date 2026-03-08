package main

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// NATSFindingsStore persists findings in a NATS KV bucket.
type NATSFindingsStore struct {
	kv jetstream.KeyValue
}

type natsEntry struct {
	ExpiresAt time.Time `json:"expires_at"`
}

func NewNATSFindingsStore(kv jetstream.KeyValue) *NATSFindingsStore {
	return &NATSFindingsStore{kv: kv}
}

func (s *NATSFindingsStore) ShouldEscalate(ctx context.Context, fingerprint string) (bool, error) {
	entry, err := s.kv.Get(ctx, fingerprint)
	if errors.Is(err, jetstream.ErrKeyNotFound) {
		return true, nil
	}
	if err != nil {
		return false, err
	}

	var e natsEntry
	if err := json.Unmarshal(entry.Value(), &e); err != nil {
		return true, nil
	}

	if time.Now().After(e.ExpiresAt) {
		_ = s.kv.Delete(ctx, fingerprint)
		return true, nil
	}
	return false, nil
}

func (s *NATSFindingsStore) MarkEscalated(ctx context.Context, fingerprint string, ttl time.Duration) error {
	data, err := json.Marshal(natsEntry{ExpiresAt: time.Now().Add(ttl)})
	if err != nil {
		return err
	}
	_, err = s.kv.Put(ctx, fingerprint, data)
	return err
}

func (s *NATSFindingsStore) MarkResolved(ctx context.Context, fingerprint string) error {
	return s.kv.Delete(ctx, fingerprint)
}

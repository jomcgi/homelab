package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

const kvBucket = "job-records"

// Store is the interface for job persistence.
type Store interface {
	Put(ctx context.Context, job *JobRecord) error
	Get(ctx context.Context, id string) (*JobRecord, error)
	Delete(ctx context.Context, id string) error
	List(ctx context.Context, statusFilter []string, limit, offset int) ([]JobRecord, int, error)
}

// JobStore implements Store using a NATS JetStream KeyValue bucket.
type JobStore struct {
	kv jetstream.KeyValue
}

// NewJobStore returns a JobStore backed by the given NATS KV bucket.
func NewJobStore(kv jetstream.KeyValue) *JobStore {
	return &JobStore{kv: kv}
}

// Put creates or updates a job record in the KV store.
func (s *JobStore) Put(ctx context.Context, job *JobRecord) error {
	job.UpdatedAt = time.Now().UTC()
	data, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("marshaling job: %w", err)
	}
	_, err = s.kv.Put(ctx, job.ID, data)
	return err
}

// Delete removes a job record from the KV store.
func (s *JobStore) Delete(ctx context.Context, id string) error {
	return s.kv.Delete(ctx, id)
}

// Get retrieves a single job record by ID.
func (s *JobStore) Get(ctx context.Context, id string) (*JobRecord, error) {
	entry, err := s.kv.Get(ctx, id)
	if err != nil {
		return nil, err
	}
	var job JobRecord
	if err := json.Unmarshal(entry.Value(), &job); err != nil {
		return nil, fmt.Errorf("unmarshaling job: %w", err)
	}
	return &job, nil
}

// List returns job records with optional status filtering and pagination.
// Jobs are sorted by key in reverse order (newest first when using ULID keys).
func (s *JobStore) List(ctx context.Context, statusFilter []string, limit, offset int) ([]JobRecord, int, error) {
	lister, err := s.kv.ListKeys(ctx)
	if err != nil {
		if err == jetstream.ErrNoKeysFound {
			return nil, 0, nil
		}
		return nil, 0, err
	}

	var keys []string
	for key := range lister.Keys() {
		keys = append(keys, key)
	}

	sort.Sort(sort.Reverse(sort.StringSlice(keys)))

	filterSet := make(map[string]bool)
	for _, f := range statusFilter {
		filterSet[strings.ToUpper(f)] = true
	}

	var all []JobRecord
	for _, key := range keys {
		entry, err := s.kv.Get(ctx, key)
		if err != nil {
			continue
		}
		var job JobRecord
		if err := json.Unmarshal(entry.Value(), &job); err != nil {
			continue
		}
		if len(filterSet) > 0 && !filterSet[string(job.Status)] {
			continue
		}
		all = append(all, job)
	}

	total := len(all)
	if offset >= total {
		return nil, total, nil
	}
	end := offset + limit
	if end > total {
		end = total
	}
	return all[offset:end], total, nil
}

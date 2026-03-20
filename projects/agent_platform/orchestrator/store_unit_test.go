package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// ---------------------------------------------------------------------------
// In-memory jetstream.KeyValue implementation for unit testing JobStore.
// ---------------------------------------------------------------------------

// inMemKV is a thread-safe, in-memory implementation of jetstream.KeyValue.
// It only implements the four methods used by JobStore; all other methods panic.
type inMemKV struct {
	mu      sync.RWMutex
	data    map[string][]byte
	putErr  error // if non-nil, Put returns this error
	getErr  error // if non-nil, Get returns this error
	delErr  error // if non-nil, Delete returns this error
	listErr error // if non-nil, ListKeys returns this error
}

func newInMemKV() *inMemKV {
	return &inMemKV{data: make(map[string][]byte)}
}

// --- Methods used by JobStore ---

func (f *inMemKV) Put(_ context.Context, key string, value []byte) (uint64, error) {
	if f.putErr != nil {
		return 0, f.putErr
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	f.data[key] = value
	return 1, nil
}

func (f *inMemKV) Get(_ context.Context, key string) (jetstream.KeyValueEntry, error) {
	if f.getErr != nil {
		return nil, f.getErr
	}
	f.mu.RLock()
	defer f.mu.RUnlock()
	val, ok := f.data[key]
	if !ok {
		return nil, jetstream.ErrKeyNotFound
	}
	return &inMemEntry{key: key, value: val}, nil
}

func (f *inMemKV) Delete(_ context.Context, key string, _ ...jetstream.KVDeleteOpt) error {
	if f.delErr != nil {
		return f.delErr
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.data, key)
	return nil
}

func (f *inMemKV) ListKeys(_ context.Context, _ ...jetstream.WatchOpt) (jetstream.KeyLister, error) {
	if f.listErr != nil {
		return nil, f.listErr
	}
	f.mu.RLock()
	defer f.mu.RUnlock()
	if len(f.data) == 0 {
		return nil, jetstream.ErrNoKeysFound
	}
	keys := make([]string, 0, len(f.data))
	for k := range f.data {
		keys = append(keys, k)
	}
	return newChanLister(keys), nil
}

// --- Unimplemented methods that satisfy jetstream.KeyValue ---

func (f *inMemKV) GetRevision(_ context.Context, _ string, _ uint64) (jetstream.KeyValueEntry, error) {
	panic("not implemented")
}

func (f *inMemKV) PutString(_ context.Context, _ string, _ string) (uint64, error) {
	panic("not implemented")
}

func (f *inMemKV) Create(_ context.Context, _ string, _ []byte, _ ...jetstream.KVCreateOpt) (uint64, error) {
	panic("not implemented")
}

func (f *inMemKV) Update(_ context.Context, _ string, _ []byte, _ uint64) (uint64, error) {
	panic("not implemented")
}

func (f *inMemKV) Purge(_ context.Context, _ string, _ ...jetstream.KVDeleteOpt) error {
	panic("not implemented")
}

func (f *inMemKV) Watch(_ context.Context, _ string, _ ...jetstream.WatchOpt) (jetstream.KeyWatcher, error) {
	panic("not implemented")
}

func (f *inMemKV) WatchAll(_ context.Context, _ ...jetstream.WatchOpt) (jetstream.KeyWatcher, error) {
	panic("not implemented")
}

func (f *inMemKV) WatchFiltered(_ context.Context, _ []string, _ ...jetstream.WatchOpt) (jetstream.KeyWatcher, error) {
	panic("not implemented")
}

func (f *inMemKV) Keys(_ context.Context, _ ...jetstream.WatchOpt) ([]string, error) {
	panic("not implemented")
}

func (f *inMemKV) ListKeysFiltered(_ context.Context, _ ...string) (jetstream.KeyLister, error) {
	panic("not implemented")
}

func (f *inMemKV) History(_ context.Context, _ string, _ ...jetstream.WatchOpt) ([]jetstream.KeyValueEntry, error) {
	panic("not implemented")
}
func (f *inMemKV) Bucket() string { return "test-bucket" }
func (f *inMemKV) PurgeDeletes(_ context.Context, _ ...jetstream.KVPurgeOpt) error {
	panic("not implemented")
}

func (f *inMemKV) Status(_ context.Context) (jetstream.KeyValueStatus, error) {
	panic("not implemented")
}

// ---------------------------------------------------------------------------
// inMemEntry implements jetstream.KeyValueEntry.
// ---------------------------------------------------------------------------

type inMemEntry struct {
	key   string
	value []byte
}

func (e *inMemEntry) Bucket() string                  { return "test-bucket" }
func (e *inMemEntry) Key() string                     { return e.key }
func (e *inMemEntry) Value() []byte                   { return e.value }
func (e *inMemEntry) Revision() uint64                { return 1 }
func (e *inMemEntry) Created() time.Time              { return time.Time{} }
func (e *inMemEntry) Delta() uint64                   { return 0 }
func (e *inMemEntry) Operation() jetstream.KeyValueOp { return jetstream.KeyValuePut }

// ---------------------------------------------------------------------------
// chanLister implements jetstream.KeyLister via a pre-populated channel.
// ---------------------------------------------------------------------------

type chanLister struct {
	ch chan string
}

func newChanLister(keys []string) *chanLister {
	ch := make(chan string, len(keys))
	for _, k := range keys {
		ch <- k
	}
	close(ch)
	return &chanLister{ch: ch}
}

func (l *chanLister) Keys() <-chan string { return l.ch }
func (l *chanLister) Stop() error         { return nil }

// ---------------------------------------------------------------------------
// Helper: build a test JobStore backed by inMemKV.
// ---------------------------------------------------------------------------

func newUnitTestStore(t *testing.T) (*JobStore, *inMemKV) {
	t.Helper()
	kv := newInMemKV()
	store := NewJobStore(kv, slog.Default())
	return store, kv
}

// ---------------------------------------------------------------------------
// hasAllTags unit tests — duplicate-tags edge case not covered elsewhere
// ---------------------------------------------------------------------------

func TestHasAllTags_DuplicateTagsInJob(t *testing.T) {
	// Duplicates in job tags shouldn't cause false negatives.
	if !hasAllTags([]string{"a", "a", "b"}, []string{"a", "b"}) {
		t.Error("expected true: all required tags present despite duplicates")
	}
}

// ---------------------------------------------------------------------------
// JobStore.Put unit tests
// ---------------------------------------------------------------------------

func TestJobStore_Put_SetsUpdatedAt(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	before := time.Now().UTC()
	job := &JobRecord{
		ID:     "job-001",
		Task:   "echo hello",
		Status: JobPending,
	}
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}
	after := time.Now().UTC()

	if job.UpdatedAt.Before(before) || job.UpdatedAt.After(after) {
		t.Errorf("UpdatedAt = %v, want between %v and %v", job.UpdatedAt, before, after)
	}
}

func TestJobStore_Put_MarshalErrorPropagated(t *testing.T) {
	// An invalid job (with a channel field) would fail marshaling, but since
	// JobRecord is a plain struct, we test the KV write error path instead.
	store, kv := newUnitTestStore(t)
	kv.putErr = fmt.Errorf("kv write failure")
	ctx := context.Background()

	job := &JobRecord{ID: "job-err", Task: "fail", Status: JobPending}
	if err := store.Put(ctx, job); err == nil {
		t.Fatal("expected error from Put when kv returns error")
	}
}

func TestJobStore_Put_Overwrite(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	job := &JobRecord{ID: "job-x", Task: "initial", Status: JobPending}
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("first Put: %v", err)
	}

	job.Status = JobRunning
	job.Task = "updated"
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("second Put: %v", err)
	}

	got, err := store.Get(ctx, "job-x")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got.Status != JobRunning {
		t.Errorf("Status = %q, want %q", got.Status, JobRunning)
	}
	if got.Task != "updated" {
		t.Errorf("Task = %q, want %q", got.Task, "updated")
	}
}

// ---------------------------------------------------------------------------
// JobStore.Get unit tests
// ---------------------------------------------------------------------------

func TestJobStore_Get_RoundTrip(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	exitCode := 42
	finished := time.Now().UTC()
	job := &JobRecord{
		ID:         "get-001",
		Task:       "run something",
		Status:     JobSucceeded,
		MaxRetries: 3,
		Source:     "ci",
		Tags:       []string{"tag1", "tag2"},
		Attempts: []Attempt{
			{
				Number:           1,
				SandboxClaimName: "sandbox-abc",
				ExitCode:         &exitCode,
				Output:           "done",
				FinishedAt:       &finished,
			},
		},
	}
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := store.Get(ctx, "get-001")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got.ID != "get-001" {
		t.Errorf("ID = %q, want get-001", got.ID)
	}
	if got.Task != "run something" {
		t.Errorf("Task = %q, want %q", got.Task, "run something")
	}
	if got.Status != JobSucceeded {
		t.Errorf("Status = %q, want SUCCEEDED", got.Status)
	}
	if got.MaxRetries != 3 {
		t.Errorf("MaxRetries = %d, want 3", got.MaxRetries)
	}
	if len(got.Tags) != 2 || got.Tags[0] != "tag1" {
		t.Errorf("Tags = %v, want [tag1 tag2]", got.Tags)
	}
	if len(got.Attempts) != 1 || *got.Attempts[0].ExitCode != 42 {
		t.Errorf("Attempts not round-tripped correctly: %+v", got.Attempts)
	}
}

func TestJobStore_Get_NotFound(t *testing.T) {
	store, _ := newUnitTestStore(t)
	_, err := store.Get(context.Background(), "nonexistent")
	if err == nil {
		t.Fatal("expected error for missing key")
	}
}

func TestJobStore_Get_CorruptJSON(t *testing.T) {
	store, kv := newUnitTestStore(t)
	ctx := context.Background()

	// Inject corrupt JSON directly into the KV.
	kv.mu.Lock()
	kv.data["bad-job"] = []byte("not-valid-json{{{")
	kv.mu.Unlock()

	_, err := store.Get(ctx, "bad-job")
	if err == nil {
		t.Fatal("expected error when JSON is corrupt")
	}
}

func TestJobStore_Get_KVError(t *testing.T) {
	store, kv := newUnitTestStore(t)
	kv.getErr = fmt.Errorf("network error")

	_, err := store.Get(context.Background(), "any-key")
	if err == nil {
		t.Fatal("expected error when kv.Get fails")
	}
}

// ---------------------------------------------------------------------------
// JobStore.Delete unit tests
// ---------------------------------------------------------------------------

func TestJobStore_Delete_RemovesRecord(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	job := &JobRecord{ID: "del-001", Task: "ephemeral", Status: JobPending}
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}
	if err := store.Delete(ctx, "del-001"); err != nil {
		t.Fatalf("Delete: %v", err)
	}

	_, err := store.Get(ctx, "del-001")
	if err == nil {
		t.Fatal("expected error after delete")
	}
}

func TestJobStore_Delete_NonexistentKeyIsNoOp(t *testing.T) {
	store, _ := newUnitTestStore(t)
	// Deleting a key that doesn't exist should not error.
	if err := store.Delete(context.Background(), "ghost-key"); err != nil {
		t.Errorf("Delete of non-existent key returned unexpected error: %v", err)
	}
}

func TestJobStore_Delete_KVError(t *testing.T) {
	store, kv := newUnitTestStore(t)
	kv.delErr = fmt.Errorf("delete failed")

	if err := store.Delete(context.Background(), "any"); err == nil {
		t.Fatal("expected error when kv.Delete fails")
	}
}

// ---------------------------------------------------------------------------
// JobStore.List unit tests
// ---------------------------------------------------------------------------

func TestJobStore_List_EmptyBucket(t *testing.T) {
	store, _ := newUnitTestStore(t)
	jobs, total, err := store.List(context.Background(), nil, nil, 100, 0)
	if err != nil {
		t.Fatalf("List on empty bucket: %v", err)
	}
	if total != 0 || len(jobs) != 0 {
		t.Errorf("got total=%d jobs=%d, want 0/0", total, len(jobs))
	}
}

func TestJobStore_List_AllJobs(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "j1", Task: "t1", Status: JobPending},
		{ID: "j2", Task: "t2", Status: JobRunning},
		{ID: "j3", Task: "t3", Status: JobSucceeded},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put(%s): %v", j.ID, err)
		}
	}

	jobs, total, err := store.List(ctx, nil, nil, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 3 {
		t.Errorf("total = %d, want 3", total)
	}
	if len(jobs) != 3 {
		t.Errorf("len(jobs) = %d, want 3", len(jobs))
	}
}

func TestJobStore_List_StatusFilter_CaseInsensitive(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "sf1", Task: "t1", Status: JobPending},
		{ID: "sf2", Task: "t2", Status: JobRunning},
		{ID: "sf3", Task: "t3", Status: JobPending},
		{ID: "sf4", Task: "t4", Status: JobFailed},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// Lowercase filter should match uppercase status values.
	jobs, total, err := store.List(ctx, []string{"pending"}, nil, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 2 {
		t.Errorf("total = %d, want 2", total)
	}
	for _, j := range jobs {
		if j.Status != JobPending {
			t.Errorf("job %s has status %q, want PENDING", j.ID, j.Status)
		}
	}
}

func TestJobStore_List_StatusFilter_MultipleStatuses(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "ms1", Task: "t1", Status: JobPending},
		{ID: "ms2", Task: "t2", Status: JobRunning},
		{ID: "ms3", Task: "t3", Status: JobSucceeded},
		{ID: "ms4", Task: "t4", Status: JobFailed},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	jobs, total, err := store.List(ctx, []string{"PENDING", "FAILED"}, nil, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 2 {
		t.Errorf("total = %d, want 2 (pending + failed)", total)
	}
	for _, j := range jobs {
		if j.Status != JobPending && j.Status != JobFailed {
			t.Errorf("job %s has unexpected status %q", j.ID, j.Status)
		}
	}
}

func TestJobStore_List_TagFilter_SingleTag(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "tf1", Task: "t1", Status: JobPending, Tags: []string{"alpha", "beta"}},
		{ID: "tf2", Task: "t2", Status: JobPending, Tags: []string{"beta"}},
		{ID: "tf3", Task: "t3", Status: JobPending, Tags: []string{"gamma"}},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	jobs, total, err := store.List(ctx, nil, []string{"beta"}, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 2 {
		t.Errorf("total = %d, want 2", total)
	}
	for _, j := range jobs {
		found := false
		for _, tag := range j.Tags {
			if tag == "beta" {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("job %s does not have tag 'beta': %v", j.ID, j.Tags)
		}
	}
}

func TestJobStore_List_TagFilter_MultipleTagsAllRequired(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "mtf1", Task: "t1", Status: JobPending, Tags: []string{"a", "b", "c"}},
		{ID: "mtf2", Task: "t2", Status: JobPending, Tags: []string{"a", "b"}},
		{ID: "mtf3", Task: "t3", Status: JobPending, Tags: []string{"b", "c"}},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// Only job mtf1 has all three tags.
	jobs, total, err := store.List(ctx, nil, []string{"a", "b", "c"}, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 1 {
		t.Errorf("total = %d, want 1", total)
	}
	if len(jobs) > 0 && jobs[0].ID != "mtf1" {
		t.Errorf("got job %q, want mtf1", jobs[0].ID)
	}
}

func TestJobStore_List_StatusAndTagFilter_Combined(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for _, j := range []*JobRecord{
		{ID: "c1", Task: "t1", Status: JobPending, Tags: []string{"env:prod"}},
		{ID: "c2", Task: "t2", Status: JobRunning, Tags: []string{"env:prod"}},
		{ID: "c3", Task: "t3", Status: JobPending, Tags: []string{"env:dev"}},
		{ID: "c4", Task: "t4", Status: JobPending, Tags: []string{}},
	} {
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// Only pending jobs with env:prod tag.
	jobs, total, err := store.List(ctx, []string{"PENDING"}, []string{"env:prod"}, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 1 {
		t.Errorf("total = %d, want 1", total)
	}
	if len(jobs) > 0 && jobs[0].ID != "c1" {
		t.Errorf("got job %q, want c1", jobs[0].ID)
	}
}

func TestJobStore_List_Pagination_BasicPages(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	for i := 0; i < 5; i++ {
		j := &JobRecord{
			ID:     fmt.Sprintf("page-%02d", i),
			Task:   fmt.Sprintf("task %d", i),
			Status: JobPending,
		}
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// Page 1.
	page1, total, err := store.List(ctx, nil, nil, 2, 0)
	if err != nil {
		t.Fatalf("List page1: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(page1) != 2 {
		t.Errorf("page1 len = %d, want 2", len(page1))
	}

	// Page 2.
	page2, total, err := store.List(ctx, nil, nil, 2, 2)
	if err != nil {
		t.Fatalf("List page2: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(page2) != 2 {
		t.Errorf("page2 len = %d, want 2", len(page2))
	}

	// Page 3 (partial).
	page3, total, err := store.List(ctx, nil, nil, 2, 4)
	if err != nil {
		t.Fatalf("List page3: %v", err)
	}
	if total != 5 {
		t.Errorf("total = %d, want 5", total)
	}
	if len(page3) != 1 {
		t.Errorf("page3 len = %d, want 1 (partial last page)", len(page3))
	}
}

func TestJobStore_List_Pagination_OffsetBeyondTotal(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	job := &JobRecord{ID: "only-one", Task: "task", Status: JobPending}
	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	jobs, total, err := store.List(ctx, nil, nil, 10, 100)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 1 {
		t.Errorf("total = %d, want 1", total)
	}
	if len(jobs) != 0 {
		t.Errorf("len(jobs) = %d, want 0 (offset beyond total)", len(jobs))
	}
}

func TestJobStore_List_SortedReverseOrder(t *testing.T) {
	store, _ := newUnitTestStore(t)
	ctx := context.Background()

	// IDs are lexicographically sortable. List should return them in reverse order.
	for _, id := range []string{"aaa", "bbb", "ccc"} {
		j := &JobRecord{ID: id, Task: "t", Status: JobPending}
		if err := store.Put(ctx, j); err != nil {
			t.Fatalf("Put(%s): %v", id, err)
		}
	}

	jobs, _, err := store.List(ctx, nil, nil, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(jobs) != 3 {
		t.Fatalf("len = %d, want 3", len(jobs))
	}
	// ccc > bbb > aaa in reverse lex order.
	if jobs[0].ID != "ccc" || jobs[1].ID != "bbb" || jobs[2].ID != "aaa" {
		t.Errorf("order = [%s %s %s], want [ccc bbb aaa]", jobs[0].ID, jobs[1].ID, jobs[2].ID)
	}
}

func TestJobStore_List_SkipsCorruptRecords(t *testing.T) {
	store, kv := newUnitTestStore(t)
	ctx := context.Background()

	// Put a valid job.
	good := &JobRecord{ID: "good-job", Task: "t", Status: JobPending}
	if err := store.Put(ctx, good); err != nil {
		t.Fatalf("Put good: %v", err)
	}

	// Inject a corrupt record directly into the KV.
	kv.mu.Lock()
	kv.data["corrupt-job"] = []byte("not-json")
	kv.mu.Unlock()

	// List should skip the corrupt record and return only the valid one.
	jobs, total, err := store.List(ctx, nil, nil, 100, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	// total only counts successfully unmarshaled records.
	if total != 1 {
		t.Errorf("total = %d, want 1 (corrupt skipped)", total)
	}
	if len(jobs) != 1 || jobs[0].ID != "good-job" {
		t.Errorf("jobs = %v, want only good-job", jobs)
	}
}

func TestJobStore_List_KVListKeysError(t *testing.T) {
	store, kv := newUnitTestStore(t)
	kv.listErr = fmt.Errorf("jetstream timeout")

	_, _, err := store.List(context.Background(), nil, nil, 100, 0)
	if err == nil {
		t.Fatal("expected error when kv.ListKeys fails")
	}
}

// ---------------------------------------------------------------------------
// JobStore.Put: verify JSON serialization of all relevant fields.
// ---------------------------------------------------------------------------

func TestJobStore_Put_JSONFieldsPreserved(t *testing.T) {
	_, kv := newUnitTestStore(t)
	store := NewJobStore(kv, slog.Default())
	ctx := context.Background()

	exitCode := 0
	finished := time.Now().UTC().Truncate(time.Second)
	job := &JobRecord{
		ID:         "full-001",
		Task:       "complex task",
		Profile:    "default",
		Status:     JobRunning,
		MaxRetries: 5,
		Source:     "api",
		Tags:       []string{"prod", "high-priority"},
		DebugMode:  true,
		Title:      "My title",
		Summary:    "My summary",
		Attempts: []Attempt{
			{
				Number:           2,
				SandboxClaimName: "sb-xyz",
				ExitCode:         &exitCode,
				Output:           "stdout output",
				Truncated:        true,
				StartedAt:        finished.Add(-10 * time.Second),
				FinishedAt:       &finished,
			},
		},
	}

	if err := store.Put(ctx, job); err != nil {
		t.Fatalf("Put: %v", err)
	}

	// Inspect what was stored in the KV directly.
	kv.mu.RLock()
	raw := kv.data["full-001"]
	kv.mu.RUnlock()

	if raw == nil {
		t.Fatal("no data stored in KV")
	}

	var decoded JobRecord
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}

	if decoded.Profile != "default" {
		t.Errorf("Profile = %q, want default", decoded.Profile)
	}
	if !decoded.DebugMode {
		t.Error("DebugMode should be true")
	}
	if decoded.Title != "My title" {
		t.Errorf("Title = %q, want 'My title'", decoded.Title)
	}
	if len(decoded.Attempts) != 1 || decoded.Attempts[0].Truncated != true {
		t.Error("Attempt.Truncated not preserved")
	}
	if decoded.MaxRetries != 5 {
		t.Errorf("MaxRetries = %d, want 5", decoded.MaxRetries)
	}
}

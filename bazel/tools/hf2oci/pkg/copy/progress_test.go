package copy

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/google/go-containerregistry/pkg/registry"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/google/go-containerregistry/pkg/v1/remote/transport"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
)

// readAll drains rc and returns (total bytes, error). Used in tests to trigger
// progressReader's EOF-triggered callback by consuming the reader fully.
func readAll(rc io.ReadCloser) (int64, error) {
	buf := make([]byte, 512)
	var total int64
	for {
		n, err := rc.Read(buf)
		total += int64(n)
		if err == io.EOF {
			return total, io.EOF
		}
		if err != nil {
			return total, err
		}
	}
}

// ---------------------------------------------------------------------------
// progressReader unit tests
// ---------------------------------------------------------------------------

func TestProgressReader_ReportsTotalBytesOnEOF(t *testing.T) {
	data := make([]byte, 1024)
	var lastRead, lastTotal int64
	pr := &progressReader{
		inner: io.NopCloser(bytes.NewReader(data)),
		total: int64(len(data)),
		onProgress: func(read, total int64) {
			lastRead = read
			lastTotal = total
		},
		interval: 100 << 20, // 100MB — much larger than test data; only EOF triggers
	}

	// Read until EOF so the progressReader sees io.EOF and fires the callback.
	_, err := readAll(pr)
	require.ErrorIs(t, err, io.EOF)

	assert.Equal(t, int64(1024), lastRead, "should report all bytes on EOF")
	assert.Equal(t, int64(1024), lastTotal, "total should match construction param")
}

func TestProgressReader_ReportsAtInterval(t *testing.T) {
	// 300 bytes of data, interval = 100 bytes → expect progress calls after
	// each 100-byte chunk.
	data := make([]byte, 300)
	var calls []int64
	pr := &progressReader{
		inner: io.NopCloser(bytes.NewReader(data)),
		total: int64(len(data)),
		onProgress: func(read, _ int64) {
			calls = append(calls, read)
		},
		interval: 100,
	}

	// Read in 100-byte chunks.
	buf := make([]byte, 100)
	for {
		_, err := pr.Read(buf)
		if err == io.EOF {
			break
		}
		require.NoError(t, err)
	}

	// Should have at least 3 progress reports (100, 200, 300/EOF).
	assert.GreaterOrEqual(t, len(calls), 3)
	// Last report must reflect all bytes read.
	assert.Equal(t, int64(300), calls[len(calls)-1])
}

func TestProgressReader_TracksBytesRead(t *testing.T) {
	data := make([]byte, 512)
	var reported int64
	pr := &progressReader{
		inner: io.NopCloser(bytes.NewReader(data)),
		total: int64(len(data)),
		onProgress: func(read, _ int64) {
			reported = read
		},
		interval: 256,
	}

	buf := make([]byte, 256)
	n, _ := pr.Read(buf)
	assert.Equal(t, 256, n)
	assert.Equal(t, int64(256), pr.read, "internal read counter should be updated")

	// Read remaining + drain to EOF.
	_, _ = readAll(pr)
	assert.Equal(t, int64(512), reported)
}

func TestProgressReader_NilCallbackNoPanic(t *testing.T) {
	// wrapProgress returns the original body when onProgress is nil;
	// verify that path does NOT return a progressReader.
	body := io.NopCloser(bytes.NewReader(make([]byte, 64)))
	result := wrapProgress(body, 64, nil)
	assert.Equal(t, body, result, "wrapProgress(nil callback) should return original body unchanged")
}

func TestProgressReader_Close(t *testing.T) {
	called := false
	rc := &closeTracker{called: &called}
	pr := &progressReader{
		inner:      rc,
		onProgress: func(_, _ int64) {},
	}
	require.NoError(t, pr.Close())
	assert.True(t, called, "Close should delegate to inner ReadCloser")
}

// ---------------------------------------------------------------------------
// shardProgressReader + aggregateProgress unit tests
// ---------------------------------------------------------------------------

func TestShardProgressReader_AccumulatesAggregate(t *testing.T) {
	// Two shards each reading 50 bytes. Verify aggregate totalRead = 100.
	var overallReads []int64
	var mu sync.Mutex

	agg := &aggregateProgress{
		totalSize:  100,
		shardCount: 2,
		onProgress: func(_, _ int, _, _, overallRead, _ int64) {
			mu.Lock()
			overallReads = append(overallReads, overallRead)
			mu.Unlock()
		},
	}

	data := make([]byte, 50)

	// Wrap two readers and drain them both so EOF fires the callback.
	r1 := agg.wrapShardProgress(io.NopCloser(bytes.NewReader(data)), 1, 50)
	r2 := agg.wrapShardProgress(io.NopCloser(bytes.NewReader(data)), 2, 50)

	_, _ = readAll(r1)
	_, _ = readAll(r2)

	agg.mu.Lock()
	total := agg.totalRead
	agg.mu.Unlock()

	assert.Equal(t, int64(100), total, "aggregate should count bytes from both shards")
}

func TestShardProgressReader_ReportsPerShardAndOverall(t *testing.T) {
	type report struct {
		index, total int
		shardRead    int64
		shardSize    int64
		overallRead  int64
		overallSize  int64
	}
	var reports []report
	var mu sync.Mutex

	agg := &aggregateProgress{
		totalSize:  200,
		shardCount: 2,
		onProgress: func(index, total int, shardRead, shardSize, overallRead, overallSize int64) {
			mu.Lock()
			reports = append(reports, report{index, total, shardRead, shardSize, overallRead, overallSize})
			mu.Unlock()
		},
	}

	data := make([]byte, 200)
	reader := agg.wrapShardProgress(io.NopCloser(bytes.NewReader(data)), 1, 200)

	// Drain the reader so EOF is reached and the callback fires.
	_, _ = readAll(reader)

	require.NotEmpty(t, reports)
	last := reports[len(reports)-1]
	assert.Equal(t, 1, last.index, "shard index should be 1")
	assert.Equal(t, 2, last.total, "shard count should match aggregateProgress.shardCount")
	assert.Equal(t, int64(200), last.shardRead, "shardRead should equal bytes read from this shard")
	assert.Equal(t, int64(200), last.shardSize)
	assert.Equal(t, int64(200), last.overallRead)
	assert.Equal(t, int64(200), last.overallSize)
}

func TestShardProgressReader_ConcurrentSafeAggregation(t *testing.T) {
	// Spin up N goroutines each reading from their own shardProgressReader.
	// After all complete, aggregate totalRead should equal N * chunkSize.
	const (
		shards    = 8
		chunkSize = 1000
	)

	var counter int64 // atomic: count onProgress calls to verify no data races
	agg := &aggregateProgress{
		totalSize:  int64(shards * chunkSize),
		shardCount: shards,
		onProgress: func(_, _ int, _, _, _, _ int64) {
			atomic.AddInt64(&counter, 1)
		},
	}

	var wg sync.WaitGroup
	for i := 0; i < shards; i++ {
		i := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			data := make([]byte, chunkSize)
			r := agg.wrapShardProgress(io.NopCloser(bytes.NewReader(data)), int64(i+1), int64(chunkSize))
			// Drain the reader fully so EOF fires the final progress report.
			_, _ = readAll(r)
		}()
	}
	wg.Wait()

	agg.mu.Lock()
	total := agg.totalRead
	agg.mu.Unlock()

	assert.Equal(t, int64(shards*chunkSize), total, "concurrent reads should sum correctly")
}

func TestShardProgressReader_NilCallbackReturnsOriginalBody(t *testing.T) {
	body := io.NopCloser(bytes.NewReader([]byte("data")))
	agg := &aggregateProgress{onProgress: nil}
	result := agg.wrapShardProgress(body, 1, 4)
	assert.Equal(t, body, result, "nil onProgress should return the original body")
}

func TestShardProgressReader_Close(t *testing.T) {
	called := false
	rc := &closeTracker{called: &called}
	agg := &aggregateProgress{
		totalSize:  10,
		shardCount: 1,
		onProgress: func(_, _ int, _, _, _, _ int64) {},
	}
	reader := agg.wrapShardProgress(rc, 1, 10)
	require.NoError(t, reader.Close())
	assert.True(t, called)
}

// ---------------------------------------------------------------------------
// buildSplitGGUFLayers: HTTP 200 fallback path
// ---------------------------------------------------------------------------

func TestCopyGGUFSplitFallbackWhen200(t *testing.T) {
	// A server that ignores Range headers and always returns 200 (not 206).
	// buildSplitGGUFLayers should detect fallback=true and fall back to a
	// single-layer download rather than failing or splitting.
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/BigModel-GGUF/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "BigModel.gguf", Size: 512},
			})
		case r.URL.Path == "/api/models/Org/BigModel-GGUF":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/BigModel-GGUF"})
		case strings.HasPrefix(r.URL.Path, "/Org/BigModel-GGUF/resolve/"):
			// Always respond with 200 even if Range header is present.
			// This triggers the fallback=true branch in DownloadRange.
			w.Header().Set("Content-Length", "512")
			w.WriteHeader(http.StatusOK) // NOT 206
			w.Write(make([]byte, 512))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	var splitCalled bool
	result, err := Copy(context.Background(), Options{
		Repo:         "Org/BigModel-GGUF",
		Registry:     regHost + "/models",
		Revision:     "main",
		MaxShardSize: 100, // tiny shard size — would split if range requests worked
		HFClient:     client,
		RemoteOpts:   []remote.Option{},
		OnGGUFSplit: func(_ int, _ string) {
			splitCalled = true
		},
	})
	require.NoError(t, err)

	// The server returned 200, so the client fell back to single-layer mode.
	// OnGGUFSplit should NOT have been called.
	assert.False(t, splitCalled, "OnGGUFSplit must not be called when server does not support range requests")
	assert.Contains(t, result.Digest, "sha256:")
	assert.False(t, result.Cached)
}

// ---------------------------------------------------------------------------
// wrapRegistryError unit tests
// ---------------------------------------------------------------------------

func TestWrapRegistryError_4xxIsPermanent(t *testing.T) {
	codes := []int{
		http.StatusBadRequest,       // 400
		http.StatusUnauthorized,     // 401
		http.StatusForbidden,        // 403
		http.StatusNotFound,         // 404
		http.StatusMethodNotAllowed, // 405
		http.StatusConflict,         // 409
	}
	for _, code := range codes {
		te := &transport.Error{StatusCode: code}
		err := wrapRegistryError(te)
		assert.True(t, IsPermanent(err), "HTTP %d should be permanent", code)
		assert.ErrorContains(t, err, "checking registry")
	}
}

func TestWrapRegistryError_429IsTransient(t *testing.T) {
	// 429 Too Many Requests is explicitly excluded from the permanent range.
	te := &transport.Error{StatusCode: http.StatusTooManyRequests}
	err := wrapRegistryError(te)
	assert.False(t, IsPermanent(err), "429 should be transient (retryable)")
	assert.ErrorContains(t, err, "checking registry")
}

func TestWrapRegistryError_5xxIsTransient(t *testing.T) {
	codes := []int{
		http.StatusInternalServerError, // 500
		http.StatusBadGateway,          // 502
		http.StatusServiceUnavailable,  // 503
		http.StatusGatewayTimeout,      // 504
	}
	for _, code := range codes {
		te := &transport.Error{StatusCode: code}
		err := wrapRegistryError(te)
		assert.False(t, IsPermanent(err), "HTTP %d should be transient", code)
	}
}

func TestWrapRegistryError_NonTransportErrorIsTransient(t *testing.T) {
	// Plain network errors (not transport.Error) should also be transient.
	plain := assert.AnError
	err := wrapRegistryError(plain)
	assert.False(t, IsPermanent(err), "non-transport error should be transient")
	assert.ErrorContains(t, err, "checking registry")
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// closeTracker is a ReadCloser that records whether Close was called.
type closeTracker struct {
	io.Reader
	called *bool
}

func (c *closeTracker) Read(p []byte) (int, error) { return 0, io.EOF }
func (c *closeTracker) Close() error               { *c.called = true; return nil }

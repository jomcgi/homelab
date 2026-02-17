package hf

import (
	"bytes"
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// rangeServer creates an httptest server that serves byte ranges from data.
func rangeServer(t *testing.T, data []byte) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/resolve/") {
			http.NotFound(w, r)
			return
		}
		rangeHdr := r.Header.Get("Range")
		if rangeHdr == "" {
			w.Header().Set("Content-Length", strconv.Itoa(len(data)))
			w.Write(data)
			return
		}
		var start, end int64
		fmt.Sscanf(rangeHdr, "bytes=%d-%d", &start, &end)
		if end >= int64(len(data)) {
			end = int64(len(data)) - 1
		}
		partial := data[start : end+1]
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(data)))
		w.Header().Set("Content-Length", strconv.Itoa(len(partial)))
		w.WriteHeader(http.StatusPartialContent)
		w.Write(partial)
	}))
}

func TestParallelDownload_ReassemblesChunksInOrder(t *testing.T) {
	// 100KB of random data, split into 10KB chunks (10 chunks, 4 workers).
	data := make([]byte, 100*1024)
	rand.Read(data)

	srv := rangeServer(t, data)
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4), // 10KB chunks, no min threshold, 4 workers
	)
	body, size, err := c.ParallelDownload(context.Background(), "test/repo", "main", "model.bin", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(data)), size)

	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.Equal(t, len(data), len(got), "reassembled size should match")
	assert.True(t, bytes.Equal(data, got), "reassembled data should match original byte-for-byte")
}

func TestParallelDownload_UsesRangeRequests(t *testing.T) {
	data := make([]byte, 50*1024) // 50KB
	rand.Read(data)

	var rangeRequests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/resolve/") {
			http.NotFound(w, r)
			return
		}
		rangeHdr := r.Header.Get("Range")
		if rangeHdr == "" {
			w.Header().Set("Content-Length", strconv.Itoa(len(data)))
			w.Write(data)
			return
		}
		rangeRequests.Add(1)
		var start, end int64
		fmt.Sscanf(rangeHdr, "bytes=%d-%d", &start, &end)
		if end >= int64(len(data)) {
			end = int64(len(data)) - 1
		}
		partial := data[start : end+1]
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(data)))
		w.Header().Set("Content-Length", strconv.Itoa(len(partial)))
		w.WriteHeader(http.StatusPartialContent)
		w.Write(partial)
	}))
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4), // 10KB chunks → 5 chunks for 50KB
	)
	body, _, err := c.ParallelDownload(context.Background(), "test/repo", "main", "model.bin", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.True(t, bytes.Equal(data, got))
	assert.Equal(t, int32(5), rangeRequests.Load(), "expected 5 range requests for 50KB/10KB")
}

func TestParallelDownload_SmallFileFallback(t *testing.T) {
	data := []byte("small file content")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Empty(t, r.Header.Get("Range"), "small file should use single-connection Download")
		w.Header().Set("Content-Length", strconv.Itoa(len(data)))
		w.Write(data)
	}))
	defer srv.Close()

	// minFileSize=1KB → 18-byte file falls back to single-connection.
	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(1024, 1024, 4),
	)
	body, size, err := c.ParallelDownload(context.Background(), "test/repo", "main", "config.json", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(data)), size)
	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.Equal(t, string(data), string(got))
}

func TestParallelDownload_ServerError(t *testing.T) {
	data := make([]byte, 50*1024) // 50KB → 5 chunks of 10KB

	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := requests.Add(1)
		if n == 3 {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte("server error"))
			return
		}
		rangeHdr := r.Header.Get("Range")
		var start, end int64
		fmt.Sscanf(rangeHdr, "bytes=%d-%d", &start, &end)
		if end >= int64(len(data)) {
			end = int64(len(data)) - 1
		}
		partial := data[start : end+1]
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(data)))
		w.Header().Set("Content-Length", strconv.Itoa(len(partial)))
		w.WriteHeader(http.StatusPartialContent)
		w.Write(partial)
	}))
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4),
	)
	body, _, err := c.ParallelDownload(context.Background(), "test/repo", "main", "model.bin", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	_, err = io.ReadAll(body)
	require.Error(t, err, "should propagate server error")
}

func TestParallelDownload_ContextCancellation(t *testing.T) {
	// Pre-cancel the context so goroutines see Done immediately.
	// No server interaction needed — HTTP requests fail with context.Canceled.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	c := NewClient(
		WithBaseURL("http://127.0.0.1:1"), // unreachable, but irrelevant with pre-canceled ctx
		WithParallelConfig(1024, 0, 2),
	)
	body, _, err := c.ParallelDownload(ctx, "test/repo", "main", "model.bin", 10*1024)
	require.NoError(t, err, "setup should succeed")
	defer body.Close()

	_, err = io.ReadAll(body)
	require.Error(t, err, "should error when context is canceled")
}

func TestParallelDownload_RangeNotSupported(t *testing.T) {
	data := make([]byte, 50*1024)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Server ignores Range header and returns 200.
		w.Header().Set("Content-Length", strconv.Itoa(len(data)))
		w.WriteHeader(http.StatusOK)
		w.Write(data)
	}))
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4),
	)
	body, _, err := c.ParallelDownload(context.Background(), "test/repo", "main", "model.bin", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	_, err = io.ReadAll(body)
	require.Error(t, err, "should error when server doesn't support range requests")
	assert.Contains(t, err.Error(), "range requests")
}

func TestParallelDownload_UnevenLastChunk(t *testing.T) {
	// 25KB with 10KB chunks → chunks of 10KB, 10KB, 5KB.
	data := make([]byte, 25*1024)
	rand.Read(data)

	srv := rangeServer(t, data)
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4),
	)
	body, size, err := c.ParallelDownload(context.Background(), "test/repo", "main", "model.bin", int64(len(data)))
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(data)), size)
	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.True(t, bytes.Equal(data, got), "should handle uneven last chunk")
}

func TestParallelDownloadRange_ReassemblesSubRange(t *testing.T) {
	// 200KB file, request range [50KB, 150KB).
	data := make([]byte, 200*1024)
	rand.Read(data)

	srv := rangeServer(t, data)
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4), // 10KB chunks, no min threshold
	)

	rangeStart := int64(50 * 1024)
	rangeEnd := int64(150*1024 - 1) // inclusive
	want := data[rangeStart : rangeEnd+1]

	body, size, err := c.ParallelDownloadRange(context.Background(), "test/repo", "main", "model.bin", rangeStart, rangeEnd)
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(want)), size)
	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.True(t, bytes.Equal(want, got), "sub-range data should match original byte-for-byte")
}

func TestParallelDownloadRange_SmallRangeFallback(t *testing.T) {
	// Range smaller than minFileSize should fall back to single DownloadRange.
	data := make([]byte, 100*1024)
	rand.Read(data)

	var rangeRequests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/resolve/") {
			http.NotFound(w, r)
			return
		}
		rangeHdr := r.Header.Get("Range")
		if rangeHdr != "" {
			rangeRequests.Add(1)
		}
		var start, end int64
		fmt.Sscanf(rangeHdr, "bytes=%d-%d", &start, &end)
		if end >= int64(len(data)) {
			end = int64(len(data)) - 1
		}
		partial := data[start : end+1]
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(data)))
		w.Header().Set("Content-Length", strconv.Itoa(len(partial)))
		w.WriteHeader(http.StatusPartialContent)
		w.Write(partial)
	}))
	defer srv.Close()

	// minFileSize=20KB, request a 10KB range → single DownloadRange call.
	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(5*1024, 20*1024, 4),
	)

	rangeStart := int64(10 * 1024)
	rangeEnd := int64(20*1024 - 1)
	want := data[rangeStart : rangeEnd+1]

	body, size, err := c.ParallelDownloadRange(context.Background(), "test/repo", "main", "model.bin", rangeStart, rangeEnd)
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(want)), size)
	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.True(t, bytes.Equal(want, got))
	assert.Equal(t, int32(1), rangeRequests.Load(), "small range should use single DownloadRange")
}

func TestParallelDownloadRange_UnevenLastChunk(t *testing.T) {
	// 100KB file, range [5KB, 30KB] with 10KB chunks → 10KB, 10KB, 6KB+1.
	data := make([]byte, 100*1024)
	rand.Read(data)

	srv := rangeServer(t, data)
	defer srv.Close()

	c := NewClient(
		WithBaseURL(srv.URL),
		WithParallelConfig(10*1024, 0, 4),
	)

	rangeStart := int64(5 * 1024)
	rangeEnd := int64(30*1024 + 500) // not aligned to chunk boundary
	want := data[rangeStart : rangeEnd+1]

	body, size, err := c.ParallelDownloadRange(context.Background(), "test/repo", "main", "model.bin", rangeStart, rangeEnd)
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(len(want)), size)
	got, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.True(t, bytes.Equal(want, got), "uneven last chunk in sub-range should be handled correctly")
}

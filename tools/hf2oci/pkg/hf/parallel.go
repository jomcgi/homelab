package hf

import (
	"context"
	"fmt"
	"io"
	"sync"
)

const (
	defaultParallelChunkSize   = int64(10 << 20) // 10MB
	defaultParallelWorkers     = 8
	defaultParallelMinFileSize = int64(50 << 20) // 50MB
)

// WithParallelConfig overrides the parallel download parameters.
// chunkSize is the byte size of each Range-request chunk.
// minFileSize is the threshold below which single-connection is used.
// workers is the max number of concurrent range-request goroutines.
func WithParallelConfig(chunkSize, minFileSize int64, workers int) Option {
	return func(c *Client) {
		c.parallelConfigured = true
		c.parallelChunkSize = chunkSize
		c.parallelMinFileSize = minFileSize
		c.parallelWorkers = workers
	}
}

func (c *Client) getParallelChunkSize() int64 {
	if c.parallelConfigured && c.parallelChunkSize > 0 {
		return c.parallelChunkSize
	}
	return defaultParallelChunkSize
}

func (c *Client) getParallelWorkers() int {
	if c.parallelConfigured && c.parallelWorkers > 0 {
		return c.parallelWorkers
	}
	return defaultParallelWorkers
}

func (c *Client) getParallelMinFileSize() int64 {
	if c.parallelConfigured {
		return c.parallelMinFileSize // 0 is valid (means "always use parallel")
	}
	return defaultParallelMinFileSize
}

// ParallelDownload fetches a file using multiple parallel HTTP Range requests
// for higher throughput. totalSize must be the known file size (e.g. from the
// Tree API). Falls back to single-connection Download for files below the
// minimum threshold. The caller must close the returned ReadCloser.
func (c *Client) ParallelDownload(ctx context.Context, repo, revision, path string, totalSize int64) (io.ReadCloser, int64, error) {
	if totalSize <= c.getParallelMinFileSize() {
		return c.Download(ctx, repo, revision, path)
	}

	chunkSize := c.getParallelChunkSize()
	workers := c.getParallelWorkers()
	numChunks := int((totalSize + chunkSize - 1) / chunkSize)

	pr, pw := io.Pipe()
	go c.downloadChunks(ctx, pw, repo, revision, path, 0, totalSize, numChunks, chunkSize, workers)
	return pr, totalSize, nil
}

// ParallelDownloadRange fetches a byte range [start, end] of a file using
// multiple parallel HTTP Range requests, the same strategy as ParallelDownload
// but scoped to a sub-range. Falls back to single-connection DownloadRange for
// ranges below the minimum threshold. The caller must close the returned
// ReadCloser.
func (c *Client) ParallelDownloadRange(ctx context.Context, repo, revision, path string, start, end int64) (io.ReadCloser, int64, error) {
	rangeSize := end - start + 1
	if rangeSize <= c.getParallelMinFileSize() {
		body, size, _, err := c.DownloadRange(ctx, repo, revision, path, start, end)
		if err != nil {
			return nil, 0, err
		}
		return body, size, nil
	}

	chunkSize := c.getParallelChunkSize()
	workers := c.getParallelWorkers()
	numChunks := int((rangeSize + chunkSize - 1) / chunkSize)

	pr, pw := io.Pipe()
	go c.downloadChunks(ctx, pw, repo, revision, path, start, rangeSize, numChunks, chunkSize, workers)
	return pr, rangeSize, nil
}

// downloadChunks dispatches parallel range-request downloads and reassembles
// the results in order, writing to the pipe. rangeStart is the absolute byte
// offset within the remote file (0 for full-file downloads); rangeSize is the
// number of bytes to download from that offset.
func (c *Client) downloadChunks(ctx context.Context, pw *io.PipeWriter, repo, revision, path string, rangeStart, rangeSize int64, numChunks int, chunkSize int64, workers int) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	type chunk struct {
		index int
		data  []byte
		err   error
	}

	results := make(chan chunk, workers)
	sem := make(chan struct{}, workers)

	// Dispatcher: launches chunk downloads with bounded concurrency.
	// IMPORTANT: wg.Wait() must complete before close(results) to prevent
	// sending to a closed channel. Defers run LIFO, so close is deferred
	// first (runs last) and wg.Wait is deferred second (runs first).
	var wg sync.WaitGroup
	go func() {
		defer close(results)
		defer wg.Wait()

		for i := 0; i < numChunks; i++ {
			select {
			case sem <- struct{}{}:
			case <-ctx.Done():
				return
			}
			wg.Add(1)
			go func(idx int) {
				defer wg.Done()
				defer func() { <-sem }()

				start := rangeStart + int64(idx)*chunkSize
				end := start + chunkSize - 1
				if end >= rangeStart+rangeSize {
					end = rangeStart + rangeSize - 1
				}

				body, _, fallback, err := c.DownloadRange(ctx, repo, revision, path, start, end)
				if err != nil {
					results <- chunk{index: idx, err: fmt.Errorf("chunk %d (%d-%d): %w", idx, start, end, err)}
					return
				}
				if fallback {
					body.Close()
					results <- chunk{index: idx, err: fmt.Errorf("server does not support range requests for %s", path)}
					return
				}

				data, err := io.ReadAll(body)
				body.Close()
				if err != nil {
					results <- chunk{index: idx, err: fmt.Errorf("reading chunk %d: %w", idx, err)}
					return
				}
				results <- chunk{index: idx, data: data}
			}(i)
		}
	}()

	// Writer: consume results and emit in order.
	pending := make(map[int][]byte)
	nextIdx := 0
	var firstErr error

	for r := range results {
		if firstErr != nil {
			continue // drain remaining after error
		}
		if r.err != nil {
			firstErr = r.err
			cancel()
			continue
		}
		pending[r.index] = r.data
		for {
			data, ok := pending[nextIdx]
			if !ok {
				break
			}
			if _, err := pw.Write(data); err != nil {
				firstErr = err
				cancel()
				break
			}
			delete(pending, nextIdx)
			nextIdx++
		}
	}

	if firstErr != nil {
		pw.CloseWithError(firstErr)
	} else if nextIdx < numChunks {
		// Dispatcher exited early (e.g. context canceled) without producing
		// all chunks. Propagate the context error.
		err := ctx.Err()
		if err == nil {
			err = fmt.Errorf("incomplete download: got %d/%d chunks", nextIdx, numChunks)
		}
		pw.CloseWithError(err)
	} else {
		pw.Close()
	}
}

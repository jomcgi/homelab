package controller

import (
	"errors"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestPermanentError_Error_FormattedError verifies that formatted errors are
// preserved correctly.
func TestPermanentError_Error_FormattedError(t *testing.T) {
	inner := fmt.Errorf("registry %s returned HTTP 404", "ghcr.io/jomcgi/models")
	pe := &PermanentError{Err: inner}

	assert.Equal(t, "registry ghcr.io/jomcgi/models returned HTTP 404", pe.Error())
}

// TestPermanentError_Unwrap_ErrorsIs verifies that errors.Is can find the
// inner sentinel through the PermanentError wrapper.
func TestPermanentError_Unwrap_ErrorsIs(t *testing.T) {
	sentinel := errors.New("sentinel")
	pe := &PermanentError{Err: sentinel}

	assert.True(t, errors.Is(pe, sentinel), "errors.Is should traverse Unwrap chain")
}

// TestPermanentError_Unwrap_ErrorsAs verifies that errors.As can extract a
// typed inner error through the Unwrap chain.
func TestPermanentError_Unwrap_ErrorsAs(t *testing.T) {
	inner := &PermanentError{Err: errors.New("inner permanent")}
	wrapped := fmt.Errorf("controller: %w", inner)

	var target *PermanentError
	require.True(t, errors.As(wrapped, &target), "errors.As should find PermanentError via Unwrap chain")
	assert.Equal(t, "inner permanent", target.Err.Error())
}

// TestIsPermanentError_False_WrappedPermanent verifies that an error that
// wraps a PermanentError via fmt.Errorf is not itself flagged as permanent —
// only a direct *PermanentError at the top level is permanent.
func TestIsPermanentError_False_WrappedPermanent(t *testing.T) {
	inner := &PermanentError{Err: errors.New("bad format")}
	wrapped := fmt.Errorf("controller: %w", inner)

	assert.False(t, IsPermanentError(wrapped),
		"a wrapper around PermanentError is not itself permanent")
}

// TestIsPermanentError_TableDriven covers the full matrix of error types with
// a single table for exhaustive documentation.
func TestIsPermanentError_TableDriven(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "nil",
			err:  nil,
			want: false,
		},
		{
			name: "plain errors.New",
			err:  errors.New("something broke"),
			want: false,
		},
		{
			name: "fmt.Errorf",
			err:  fmt.Errorf("retry later"),
			want: false,
		},
		{
			name: "PermanentError with simple inner",
			err:  &PermanentError{Err: errors.New("404 not found")},
			want: true,
		},
		{
			name: "PermanentError with formatted inner",
			err:  &PermanentError{Err: fmt.Errorf("unsupported format: %s", "bin")},
			want: true,
		},
		{
			name: "PermanentError wrapping another PermanentError",
			err: &PermanentError{
				Err: &PermanentError{Err: errors.New("inner permanent")},
			},
			want: true,
		},
		{
			name: "regular error wrapping a PermanentError",
			err:  fmt.Errorf("outer: %w", &PermanentError{Err: errors.New("inner")}),
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IsPermanentError(tt.err)
			assert.Equal(t, tt.want, got)
		})
	}
}

// TestResolveResult_ZeroValue verifies that a zero-value ResolveResult is
// valid and has predictable field defaults.
func TestResolveResult_ZeroValue(t *testing.T) {
	var r ResolveResult

	assert.Empty(t, r.Ref)
	assert.Empty(t, r.Digest)
	assert.False(t, r.Cached)
	assert.Empty(t, r.Revision)
	assert.Empty(t, r.Format)
	assert.Equal(t, 0, r.FileCount)
	assert.Equal(t, int64(0), r.TotalSize)
}

// TestResolveResult_CacheHit verifies a fully-populated cache-hit result.
func TestResolveResult_CacheHit(t *testing.T) {
	r := ResolveResult{
		Ref:       "ghcr.io/jomcgi/models/llama-3.2:rev-main",
		Digest:    "sha256:abc123",
		Cached:    true,
		Revision:  "main",
		Format:    "gguf",
		FileCount: 3,
		TotalSize: 4_294_967_296, // 4 GiB
	}

	assert.Equal(t, "ghcr.io/jomcgi/models/llama-3.2:rev-main", r.Ref)
	assert.Equal(t, "sha256:abc123", r.Digest)
	assert.True(t, r.Cached)
	assert.Equal(t, "main", r.Revision)
	assert.Equal(t, "gguf", r.Format)
	assert.Equal(t, 3, r.FileCount)
	assert.Equal(t, int64(4_294_967_296), r.TotalSize)
}

// TestResolveResult_CacheMiss verifies a cache-miss result has no digest but
// still carries metadata.
func TestResolveResult_CacheMiss(t *testing.T) {
	r := ResolveResult{
		Ref:       "ghcr.io/jomcgi/models/llama-3.2:rev-main",
		Digest:    "", // not yet synced
		Cached:    false,
		Revision:  "main",
		Format:    "safetensors",
		FileCount: 10,
		TotalSize: 8_589_934_592, // 8 GiB
	}

	assert.Empty(t, r.Digest, "cache miss should have no digest")
	assert.False(t, r.Cached)
	assert.Equal(t, "safetensors", r.Format)
}

func TestPermanentError_Error(t *testing.T) {
	inner := errors.New("model not found on HuggingFace")
	pe := &PermanentError{Err: inner}
	assert.Equal(t, "model not found on HuggingFace", pe.Error())
}

func TestPermanentError_Unwrap(t *testing.T) {
	inner := errors.New("unsupported format")
	pe := &PermanentError{Err: inner}
	assert.Equal(t, inner, pe.Unwrap())
	// errors.Is traverses the Unwrap chain, so it should find the inner error.
	assert.True(t, errors.Is(pe, inner))
}

func TestPermanentError_ErrorMatchesInner(t *testing.T) {
	// Verify Error() delegates to the inner error's message.
	inner := fmt.Errorf("repo %q returned 404", "org/model")
	pe := &PermanentError{Err: inner}
	assert.Equal(t, inner.Error(), pe.Error())
}

func TestIsPermanentError_DirectPermanentError(t *testing.T) {
	pe := &PermanentError{Err: errors.New("bad model")}
	assert.True(t, IsPermanentError(pe))
}

func TestIsPermanentError_RegularError(t *testing.T) {
	err := errors.New("transient network error")
	assert.False(t, IsPermanentError(err))
}

func TestIsPermanentError_Nil(t *testing.T) {
	assert.False(t, IsPermanentError(nil))
}

func TestIsPermanentError_WrappedDoesNotMatch(t *testing.T) {
	// IsPermanentError uses a direct type assertion, not errors.As.
	// A PermanentError wrapped inside another error should return false.
	pe := &PermanentError{Err: errors.New("404")}
	wrapped := fmt.Errorf("controller: %w", pe)
	assert.False(t, IsPermanentError(wrapped),
		"IsPermanentError does not traverse the error chain")
}

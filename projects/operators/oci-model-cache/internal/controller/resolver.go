package controller

import "context"

// Resolver checks whether a model exists in the target OCI registry.
// The controller depends on this interface, not hf2oci directly.
// The concrete adapter lives in cmd/main.go — the only file that imports hf2oci.
type Resolver interface {
	Resolve(ctx context.Context, repo, registry, revision, file string) (*ResolveResult, error)
}

// ResolveResult contains the outcome of a resolve operation.
type ResolveResult struct {
	// Ref is the full OCI reference (e.g. "ghcr.io/jomcgi/models/llama-3.2:rev-main")
	Ref string

	// Digest is the OCI manifest digest (empty if not cached)
	Digest string

	// Cached is true if the model already exists in the registry
	Cached bool

	// Revision is the resolved HuggingFace revision
	Revision string

	// Format is the detected model format ("gguf", "safetensors")
	Format string

	// FileCount is the total number of files in the model
	FileCount int

	// TotalSize is the total size in bytes
	TotalSize int64
}

// PermanentError marks an error as non-retryable (404, 401, bad format).
type PermanentError struct {
	Err error
}

func (e *PermanentError) Error() string { return e.Err.Error() }
func (e *PermanentError) Unwrap() error { return e.Err }

// IsPermanentError checks if the error is a PermanentError.
func IsPermanentError(err error) bool {
	_, ok := err.(*PermanentError)
	return ok
}

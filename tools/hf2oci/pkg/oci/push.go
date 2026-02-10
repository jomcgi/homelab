package oci

import (
	"context"
	"fmt"

	"github.com/google/go-containerregistry/pkg/name"
	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/remote"
)

// CheckExists checks if a tag already exists in the registry.
// Returns the digest and true if found, empty string and false if not.
func CheckExists(_ context.Context, ref name.Reference, opts ...remote.Option) (string, bool, error) {
	desc, err := remote.Head(ref, opts...)
	if err != nil {
		// Treat all errors as "not found" - could be 404, auth issue on HEAD, etc.
		// The push will surface real auth errors.
		return "", false, nil
	}
	return desc.Digest.String(), true, nil
}

// PushIndex pushes a multi-platform image index to a registry.
// Returns the digest of the pushed index.
func PushIndex(_ context.Context, ref name.Reference, idx v1.ImageIndex, opts ...remote.Option) (string, error) {
	if err := remote.WriteIndex(ref, idx, opts...); err != nil {
		return "", fmt.Errorf("pushing index to %s: %w", ref, err)
	}

	digest, err := idx.Digest()
	if err != nil {
		return "", fmt.Errorf("computing index digest: %w", err)
	}

	return digest.String(), nil
}

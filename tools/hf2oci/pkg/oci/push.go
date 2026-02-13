package oci

import (
	"context"
	"errors"
	"fmt"
	"net/http"

	"github.com/google/go-containerregistry/pkg/name"
	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/google/go-containerregistry/pkg/v1/remote/transport"
)

// CheckExists checks if a tag already exists in the registry.
// Returns the digest and true if found, empty string and false if not.
// 404, 401, and 403 are treated as "not found" because registries like GHCR
// return DENIED/UNAUTHORIZED for packages that have never been pushed.
func CheckExists(_ context.Context, ref name.Reference, opts ...remote.Option) (string, bool, error) {
	desc, err := remote.Head(ref, opts...)
	if err != nil {
		var te *transport.Error
		if errors.As(err, &te) {
			switch te.StatusCode {
			case http.StatusNotFound, http.StatusUnauthorized, http.StatusForbidden:
				return "", false, nil
			}
		}
		// Propagate 5xx, network errors so callers can react.
		return "", false, fmt.Errorf("checking %s: %w", ref, err)
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

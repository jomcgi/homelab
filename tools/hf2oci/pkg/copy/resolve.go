package copy

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/go-containerregistry/pkg/authn"
	"github.com/google/go-containerregistry/pkg/name"
	"github.com/google/go-containerregistry/pkg/v1/remote"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/oci"
)

// ResolveOptions configures the resolve operation.
type ResolveOptions struct {
	Repo     string // HuggingFace repo (e.g. "Org/Model")
	Registry string // Target OCI registry
	Revision string // HF revision (default "main")
	Tag      string // OCI tag override

	HFClient   *hf.Client
	RemoteOpts []remote.Option
}

// Resolve checks whether a HuggingFace model already exists in the target
// registry without downloading or pushing anything.
// It lists the repo, classifies files, derives the OCI reference, and performs
// a HEAD request against the registry.
func Resolve(ctx context.Context, opts ResolveOptions) (*Result, error) {
	if opts.Revision == "" {
		opts.Revision = "main"
	}

	client := opts.HFClient
	if client == nil {
		return nil, fmt.Errorf("HFClient is required")
	}

	// 1. List files.
	entries, err := client.Tree(ctx, opts.Repo, opts.Revision)
	if err != nil {
		wrapped := fmt.Errorf("listing repo: %w", err)
		var apiErr *hf.APIError
		if errors.As(err, &apiErr) && apiErr.IsClientError() {
			return nil, Permanent(wrapped)
		}
		return nil, wrapped
	}

	// 2. Classify files.
	configs, weights, format, err := Classify(entries)
	if err != nil {
		return nil, Permanent(fmt.Errorf("classifying files: %w", err))
	}

	// 3. Derive tag and ref.
	tag := DeriveTag(opts.Tag, opts.Revision)
	repoName := deriveRepoName(opts.Repo)
	refStr := fmt.Sprintf("%s/%s:%s", opts.Registry, repoName, tag)

	fileCount := len(configs) + len(weights)
	var totalSize int64
	for _, e := range configs {
		totalSize += e.Size
	}
	for _, e := range weights {
		totalSize += e.Size
	}

	ref, err := name.ParseReference(refStr)
	if err != nil {
		return nil, Permanent(fmt.Errorf("parsing reference %q: %w", refStr, err))
	}

	remoteOpts := opts.RemoteOpts
	if remoteOpts == nil {
		remoteOpts = []remote.Option{remote.WithAuthFromKeychain(authn.DefaultKeychain)}
	}

	// 4. Check registry.
	digest, exists, err := oci.CheckExists(ctx, ref, remoteOpts...)
	if err != nil {
		return nil, fmt.Errorf("checking registry: %w", err)
	}

	return &Result{
		Ref:       refStr,
		Digest:    digest,
		Cached:    exists,
		Repo:      opts.Repo,
		Revision:  opts.Revision,
		Format:    format,
		FileCount: fileCount,
		TotalSize: totalSize,
	}, nil
}

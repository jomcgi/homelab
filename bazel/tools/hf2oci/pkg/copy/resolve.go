package copy

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/google/go-containerregistry/pkg/authn"
	"github.com/google/go-containerregistry/pkg/name"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/google/go-containerregistry/pkg/v1/remote/transport"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/oci"
	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/ociref"
)

// ResolveOptions configures the resolve operation.
type ResolveOptions struct {
	Repo          string // HuggingFace repo (e.g. "Org/Model")
	Registry      string // Target OCI registry
	Revision      string // HF revision (default "main")
	Tag           string // OCI tag override
	File          string // GGUF filename prefix selector
	IncludeMMProj bool   // Include mmproj GGUF alongside file-selected weights

	HFClient   *hf.Client
	RemoteOpts []remote.Option
}

// resolvedModel holds the intermediate state after listing, classifying, and
// deriving the OCI reference. Shared by both Copy and Resolve to avoid
// duplicating the pipeline.
type resolvedModel struct {
	ref        name.Reference
	refStr     string
	configs    []hf.TreeEntry
	weights    []hf.TreeEntry
	format     ModelFormat
	fileCount  int
	totalSize  int64
	remoteOpts []remote.Option
}

// isMMProj returns true if the filename is a multimodal projector GGUF.
func isMMProj(path string) bool {
	return strings.HasPrefix(strings.ToLower(filepath.Base(path)), "mmproj")
}

// resolveModel runs the shared list → classify → filter → derive-tag → parse-ref
// pipeline used by both Copy and Resolve.
func resolveModel(ctx context.Context, client *hf.Client, repo, registry, revision, tag, file string, includeMMProj bool, remoteOpts []remote.Option) (*resolvedModel, error) {
	// 1. List files.
	entries, err := client.Tree(ctx, repo, revision)
	if err != nil {
		wrapped := fmt.Errorf("listing repo: %w", err)
		var apiErr *hf.APIError
		if errors.As(err, &apiErr) && apiErr.IsClientError() && !apiErr.IsRetryable() {
			return nil, Permanent(wrapped)
		}
		return nil, wrapped
	}

	// 2. Classify files.
	configs, weights, format, err := Classify(entries)
	if err != nil {
		return nil, Permanent(fmt.Errorf("classifying files: %w", err))
	}

	// 3. Filter GGUF weights by file selector.
	if format == FormatGGUF {
		if file != "" {
			// Exact prefix match: file + ".gguf"
			target := file + ".gguf"
			var filtered []hf.TreeEntry
			for _, w := range weights {
				if strings.EqualFold(w.Path, target) {
					filtered = append(filtered, w)
				} else if includeMMProj && isMMProj(w.Path) {
					filtered = append(filtered, w)
				}
			}
			if len(filtered) == 0 {
				return nil, Permanent(fmt.Errorf("GGUF file selector %q matched no files in repo (have: %s)", file, ggufFileList(weights)))
			}
			weights = filtered
		} else if len(weights) > 1 {
			// When no file selector, check if the "extra" files are just mmproj.
			// If so, no ambiguity — the user wants the model + projector.
			nonMMProj := 0
			for _, w := range weights {
				if !isMMProj(w.Path) {
					nonMMProj++
				}
			}
			if nonMMProj > 1 {
				return nil, Permanent(fmt.Errorf("GGUF repo has %d quantization variants; specify one with :filename (e.g., :ModelName-Q4_K_M). Available: %s", len(weights), ggufFileList(weights)))
			}
		}
	}

	// 4. Fetch model info for smart naming (non-fatal on failure).
	var repoPath, ociTag string
	info, infoErr := client.ModelInfo(ctx, repo)
	if infoErr == nil && info.BaseModels != nil && len(info.BaseModels.Models) > 0 {
		// Derivative model: group under base model's repo path for layer dedup.
		repoPath = ociref.DeriveRepoName(info.BaseModels.Models[0].ID)
		if file != "" {
			ociTag = ociref.DeriveFileTag(info, string(format), file)
		} else {
			ociTag = ociref.DeriveVariantTag(repo)
		}
	} else {
		// Base model or ModelInfo unavailable: use repo directly.
		repoPath = ociref.DeriveRepoName(repo)
		if file != "" {
			ociTag = ociref.DeriveFileTag(info, string(format), file)
		} else {
			ociTag = ociref.DeriveTag(tag, revision)
		}
	}

	// Differentiate the tag when mmproj files are included, so that
	// "model-Q4_K_M" and "model-Q4_K_M + mmproj" don't collide in the
	// registry and silently cache-hit the wrong image.
	for _, w := range weights {
		if isMMProj(w.Path) {
			ociTag += "-mmproj"
			break
		}
	}

	refStr := fmt.Sprintf("%s/%s:%s", registry, repoPath, ociTag)

	ref, err := name.ParseReference(refStr)
	if err != nil {
		return nil, Permanent(fmt.Errorf("parsing reference %q: %w", refStr, err))
	}

	// 5. Compute totals.
	fileCount := len(configs) + len(weights)
	var totalSize int64
	for _, e := range configs {
		totalSize += e.Size
	}
	for _, e := range weights {
		totalSize += e.Size
	}

	if remoteOpts == nil {
		remoteOpts = []remote.Option{remote.WithAuthFromKeychain(authn.DefaultKeychain)}
	}

	return &resolvedModel{
		ref:        ref,
		refStr:     refStr,
		configs:    configs,
		weights:    weights,
		format:     format,
		fileCount:  fileCount,
		totalSize:  totalSize,
		remoteOpts: remoteOpts,
	}, nil
}

// ggufFileList returns a comma-separated list of GGUF filenames (without extension)
// for use in error messages.
func ggufFileList(weights []hf.TreeEntry) string {
	names := make([]string, len(weights))
	for i, w := range weights {
		names[i] = strings.TrimSuffix(w.Path, ".gguf")
	}
	return strings.Join(names, ", ")
}

// Resolve checks whether a HuggingFace model already exists in the target
// registry without downloading or pushing anything.
// It lists the repo, classifies files, derives the OCI reference, and performs
// a HEAD request against the registry.
func Resolve(ctx context.Context, opts ResolveOptions) (*Result, error) {
	if opts.Revision == "" {
		opts.Revision = "main"
	}
	if opts.HFClient == nil {
		return nil, fmt.Errorf("HFClient is required")
	}

	rm, err := resolveModel(ctx, opts.HFClient, opts.Repo, opts.Registry, opts.Revision, opts.Tag, opts.File, opts.IncludeMMProj, opts.RemoteOpts)
	if err != nil {
		return nil, err
	}

	// Check registry.
	digest, exists, err := oci.CheckExists(ctx, rm.ref, rm.remoteOpts...)
	if err != nil {
		return nil, wrapRegistryError(err)
	}

	return &Result{
		Ref:       rm.refStr,
		Digest:    digest,
		Cached:    exists,
		Repo:      opts.Repo,
		Revision:  opts.Revision,
		Format:    rm.format,
		FileCount: rm.fileCount,
		TotalSize: rm.totalSize,
	}, nil
}

// wrapRegistryError classifies registry errors: 4xx are permanent (bad
// credentials, forbidden), everything else (5xx, network) is transient.
func wrapRegistryError(err error) error {
	wrapped := fmt.Errorf("checking registry: %w", err)
	var te *transport.Error
	if errors.As(err, &te) && te.StatusCode >= http.StatusBadRequest &&
		te.StatusCode < http.StatusInternalServerError &&
		te.StatusCode != http.StatusTooManyRequests {
		return Permanent(wrapped)
	}
	return wrapped
}

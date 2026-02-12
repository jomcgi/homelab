package copy

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/google/go-containerregistry/pkg/authn"
	"github.com/google/go-containerregistry/pkg/name"
	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/remote"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/oci"
)

// Options configures the copy operation.
type Options struct {
	Repo     string // HuggingFace repo (e.g. "NousResearch/Hermes-3-8B")
	Registry string // Target registry (e.g. "ghcr.io/jomcgi/models")
	Revision string // HF revision (default "main")
	Tag      string // OCI tag override (default "rev-{revision[:12]}")
	ModelDir string // In-image model path (default "/models/{repo-name}")
	DryRun   bool

	// Callbacks for progress reporting.
	OnResolve      func(repo, revision string)
	OnClassified   func(configs, weights int, format ModelFormat)
	OnTarget       func(ref string)
	OnCacheHit     func(digest string)
	OnUploadConfig func(count int)
	OnUploadWeight func(index, total int, filename string)

	// Injected dependencies (for testing).
	HFClient   *hf.Client
	RemoteOpts []remote.Option
}

// Result contains the output of a successful copy or resolve operation.
type Result struct {
	Ref       string      `json:"ref"`
	Digest    string      `json:"digest,omitempty"`
	Cached    bool        `json:"cached"`
	Repo      string      `json:"repo"`
	Revision  string      `json:"revision"`
	Format    ModelFormat `json:"format"`
	FileCount int         `json:"fileCount"`
	TotalSize int64       `json:"totalSize"`
}

// Copy copies a HuggingFace model to an OCI registry.
func Copy(ctx context.Context, opts Options) (*Result, error) {
	if opts.Revision == "" {
		opts.Revision = "main"
	}

	client := opts.HFClient
	if client == nil {
		return nil, fmt.Errorf("HFClient is required")
	}

	if opts.OnResolve != nil {
		opts.OnResolve(opts.Repo, opts.Revision)
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

	if opts.OnClassified != nil {
		opts.OnClassified(len(configs), len(weights), format)
	}

	// 3. Derive tag and ref.
	tag := DeriveTag(opts.Tag, opts.Revision)
	repoName := deriveRepoName(opts.Repo)
	refStr := fmt.Sprintf("%s/%s:%s", opts.Registry, repoName, tag)

	// Compute totals for the enriched result.
	fileCount := len(configs) + len(weights)
	var totalSize int64
	for _, e := range configs {
		totalSize += e.Size
	}
	for _, e := range weights {
		totalSize += e.Size
	}

	if opts.OnTarget != nil {
		opts.OnTarget(refStr)
	}

	if opts.DryRun {
		return &Result{
			Ref:       refStr,
			Repo:      opts.Repo,
			Revision:  opts.Revision,
			Format:    format,
			FileCount: fileCount,
			TotalSize: totalSize,
		}, nil
	}

	ref, err := name.ParseReference(refStr)
	if err != nil {
		return nil, Permanent(fmt.Errorf("parsing reference %q: %w", refStr, err))
	}

	remoteOpts := opts.RemoteOpts
	if remoteOpts == nil {
		remoteOpts = []remote.Option{remote.WithAuthFromKeychain(authn.DefaultKeychain)}
	}

	// 4. Check cache.
	digest, exists, err := oci.CheckExists(ctx, ref, remoteOpts...)
	if err != nil {
		return nil, fmt.Errorf("checking registry: %w", err)
	}
	if exists {
		if opts.OnCacheHit != nil {
			opts.OnCacheHit(digest)
		}
		return &Result{
			Ref:       refStr,
			Digest:    digest,
			Cached:    true,
			Repo:      opts.Repo,
			Revision:  opts.Revision,
			Format:    format,
			FileCount: fileCount,
			TotalSize: totalSize,
		}, nil
	}

	// 5. Build config layer.
	modelDir := opts.ModelDir
	if modelDir == "" {
		modelDir = "/models/" + repoName
	}

	var cfgLayer v1.Layer
	if len(configs) > 0 {
		if opts.OnUploadConfig != nil {
			opts.OnUploadConfig(len(configs))
		}
		cfgFiles := make(map[string][]byte)
		for _, c := range configs {
			body, _, err := client.Download(ctx, opts.Repo, opts.Revision, c.Path)
			if err != nil {
				return nil, fmt.Errorf("downloading config %s: %w", c.Path, err)
			}
			data, err := io.ReadAll(body)
			body.Close()
			if err != nil {
				return nil, fmt.Errorf("reading config %s: %w", c.Path, err)
			}
			cfgFiles[c.Path] = data
		}
		cfgLayer, err = oci.ConfigLayer(cfgFiles, modelDir)
		if err != nil {
			return nil, fmt.Errorf("building config layer: %w", err)
		}
	}

	// 6. Build streaming weight layers.
	weightLayers := make([]v1.Layer, len(weights))
	for i, w := range weights {
		if opts.OnUploadWeight != nil {
			opts.OnUploadWeight(i+1, len(weights), w.Path)
		}
		body, size, err := client.Download(ctx, opts.Repo, opts.Revision, w.Path)
		if err != nil {
			return nil, fmt.Errorf("downloading weight %s: %w", w.Path, err)
		}
		weightLayers[i] = oci.StreamingWeightLayer(body, size, modelDir, w.Path)
	}

	// 7. Build index.
	annotations := map[string]string{
		"org.huggingface.repo":     opts.Repo,
		"org.huggingface.revision": opts.Revision,
	}
	idx, err := oci.BuildIndex(cfgLayer, weightLayers, annotations)
	if err != nil {
		return nil, fmt.Errorf("building OCI index: %w", err)
	}

	// 8. Push.
	digest, err = oci.PushIndex(ctx, ref, idx, remoteOpts...)
	if err != nil {
		return nil, fmt.Errorf("pushing: %w", err)
	}

	return &Result{
		Ref:       refStr,
		Digest:    digest,
		Repo:      opts.Repo,
		Revision:  opts.Revision,
		Format:    format,
		FileCount: fileCount,
		TotalSize: totalSize,
	}, nil
}

// DeriveTag returns the OCI tag to use. If tag is non-empty it is returned as-is;
// otherwise it is derived from revision as "rev-{revision[:12]}".
func DeriveTag(tag, revision string) string {
	if tag != "" {
		return tag
	}
	rev := revision
	if len(rev) > 12 {
		rev = rev[:12]
	}
	return "rev-" + rev
}

// deriveRepoName converts a HuggingFace repo name to a valid OCI repo path component.
// e.g. "NousResearch/Hermes-4.3-Llama-3-36B-AWQ" → "nousresearch-hermes-4.3-llama-3-36b-awq"
func deriveRepoName(repo string) string {
	return strings.ToLower(strings.ReplaceAll(repo, "/", "-"))
}

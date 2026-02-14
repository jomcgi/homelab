package copy

import (
	"context"
	"fmt"
	"io"
	"strings"
	"sync"

	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"golang.org/x/sync/errgroup"

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
// TotalSize reflects HuggingFace source file sizes, not OCI layer sizes
// after tar wrapping.
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

	// 1-3. List, classify, derive ref.
	rm, err := resolveModel(ctx, client, opts.Repo, opts.Registry, opts.Revision, opts.Tag, opts.RemoteOpts)
	if err != nil {
		return nil, err
	}

	if opts.OnClassified != nil {
		opts.OnClassified(len(rm.configs), len(rm.weights), rm.format)
	}

	if opts.OnTarget != nil {
		opts.OnTarget(rm.refStr)
	}

	if opts.DryRun {
		return &Result{
			Ref:       rm.refStr,
			Repo:      opts.Repo,
			Revision:  opts.Revision,
			Format:    rm.format,
			FileCount: rm.fileCount,
			TotalSize: rm.totalSize,
		}, nil
	}

	// 4. Check cache.
	digest, exists, err := oci.CheckExists(ctx, rm.ref, rm.remoteOpts...)
	if err != nil {
		return nil, wrapRegistryError(err)
	}
	if exists {
		if opts.OnCacheHit != nil {
			opts.OnCacheHit(digest)
		}
		return &Result{
			Ref:       rm.refStr,
			Digest:    digest,
			Cached:    true,
			Repo:      opts.Repo,
			Revision:  opts.Revision,
			Format:    rm.format,
			FileCount: rm.fileCount,
			TotalSize: rm.totalSize,
		}, nil
	}

	// 5. Build config layer.
	repoName := deriveRepoName(opts.Repo)
	modelDir := opts.ModelDir
	if modelDir == "" {
		modelDir = "/models/" + repoName
	}

	var cfgLayer v1.Layer
	if len(rm.configs) > 0 {
		if opts.OnUploadConfig != nil {
			opts.OnUploadConfig(len(rm.configs))
		}
		cfgFiles := make(map[string][]byte)
		for _, c := range rm.configs {
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

	// 6. Build streaming weight layers (parallel connection establishment).
	// NOTE: We use the parent ctx (not the errgroup's derived context) for
	// downloads because the response bodies are consumed lazily during push.
	// The errgroup context is canceled when Wait() returns, which would kill
	// the in-flight reads from the response bodies.
	weightLayers := make([]v1.Layer, len(rm.weights))
	g, _ := errgroup.WithContext(ctx)
	g.SetLimit(5) // max 5 concurrent HuggingFace connections
	var progressMu sync.Mutex
	for i, w := range rm.weights {
		i, w := i, w // capture for closure
		g.Go(func() error {
			if opts.OnUploadWeight != nil {
				progressMu.Lock()
				opts.OnUploadWeight(i+1, len(rm.weights), w.Path)
				progressMu.Unlock()
			}
			body, size, err := client.Download(ctx, opts.Repo, opts.Revision, w.Path)
			if err != nil {
				return fmt.Errorf("downloading weight %s: %w", w.Path, err)
			}
			weightLayers[i] = oci.StreamingWeightLayer(body, size, modelDir, w.Path)
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return nil, err
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
	digest, err = oci.PushIndex(ctx, rm.ref, idx, rm.remoteOpts...)
	if err != nil {
		return nil, fmt.Errorf("pushing: %w", err)
	}

	return &Result{
		Ref:       rm.refStr,
		Digest:    digest,
		Repo:      opts.Repo,
		Revision:  opts.Revision,
		Format:    rm.format,
		FileCount: rm.fileCount,
		TotalSize: rm.totalSize,
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

// deriveRepoName converts a HuggingFace repo name to an OCI repo path,
// preserving the org/model structure for cleaner registry organization.
// e.g. "NousResearch/Hermes-4.3-Llama-3-36B-AWQ" → "nousresearch/hermes-4.3-llama-3-36b-awq"
func deriveRepoName(repo string) string {
	return strings.ToLower(repo)
}

// deriveVariantTag flattens a HuggingFace repo name into a valid OCI tag.
// Used for derivative models to encode the variant identity in the tag.
// e.g. "Emilio407/nllb-200-distilled-1.3B-4bit" → "emilio407-nllb-200-distilled-1.3b-4bit"
func deriveVariantTag(repo string) string {
	return strings.ToLower(strings.ReplaceAll(repo, "/", "-"))
}

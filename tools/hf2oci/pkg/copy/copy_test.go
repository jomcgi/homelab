package copy

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/google/go-containerregistry/pkg/name"
	"github.com/google/go-containerregistry/pkg/registry"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

func TestCopySafetensors(t *testing.T) {
	// Mock HF server.
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/TestOrg/TestModel/tree/abc123def456":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 100},
				{Type: "file", Path: "tokenizer.json", Size: 200},
				{Type: "file", Path: "model.safetensors", Size: 1024},
				{Type: "file", Path: "README.md", Size: 50},
			})
		case r.URL.Path == "/TestOrg/TestModel/resolve/abc123def456/config.json":
			w.Write([]byte(`{"model_type":"test"}`))
		case r.URL.Path == "/TestOrg/TestModel/resolve/abc123def456/tokenizer.json":
			w.Write([]byte(`{"version":"1.0"}`))
		case r.URL.Path == "/TestOrg/TestModel/resolve/abc123def456/model.safetensors":
			w.Header().Set("Content-Length", "1024")
			w.Write(make([]byte, 1024))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	// In-memory OCI registry.
	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	ctx := context.Background()
	result, err := Copy(ctx, Options{
		Repo:       "TestOrg/TestModel",
		Registry:   regHost + "/models",
		Revision:   "abc123def456",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.NoError(t, err)

	assert.Equal(t, regHost+"/models/testorg-testmodel:rev-abc123def456", result.Ref)
	assert.Contains(t, result.Digest, "sha256:")
	assert.False(t, result.Cached)
	assert.Equal(t, "TestOrg/TestModel", result.Repo)
	assert.Equal(t, "abc123def456", result.Revision)
	assert.Equal(t, FormatSafetensors, result.Format)
	assert.Equal(t, 3, result.FileCount) // 2 configs + 1 weight
	assert.Equal(t, int64(1324), result.TotalSize)

	// Verify it was actually pushed.
	ref, err := name.ParseReference(result.Ref)
	require.NoError(t, err)
	idx, err := remote.Index(ref)
	require.NoError(t, err)
	mf, err := idx.IndexManifest()
	require.NoError(t, err)
	assert.Len(t, mf.Manifests, 2, "should have 2 platforms")
	assert.Equal(t, "TestOrg/TestModel", mf.Annotations["org.huggingface.repo"])
}

func TestCopyGGUF(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Qwen/Qwen2.5-GGUF/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "model-q4.gguf", Size: 512},
				{Type: "file", Path: "README.md", Size: 50},
			})
		case r.URL.Path == "/Qwen/Qwen2.5-GGUF/resolve/main/model-q4.gguf":
			w.Header().Set("Content-Length", "512")
			w.Write(make([]byte, 512))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	result, err := Copy(context.Background(), Options{
		Repo:       "Qwen/Qwen2.5-GGUF",
		Registry:   regHost + "/models",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.NoError(t, err)

	assert.Equal(t, regHost+"/models/qwen-qwen2.5-gguf:rev-main", result.Ref)
	assert.False(t, result.Cached)
}

func TestCopyCacheHit(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/rev1":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "model.safetensors", Size: 256},
			})
		case r.URL.Path == "/Org/Model/resolve/rev1/model.safetensors":
			w.Header().Set("Content-Length", "256")
			w.Write(make([]byte, 256))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	opts := Options{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "rev1",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	}

	// First copy.
	result1, err := Copy(context.Background(), opts)
	require.NoError(t, err)
	assert.False(t, result1.Cached)

	// Second copy should be a cache hit.
	result2, err := Copy(context.Background(), opts)
	require.NoError(t, err)
	assert.True(t, result2.Cached)
	assert.Equal(t, result1.Digest, result2.Digest)
}

func TestCopyDryRun(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]hf.TreeEntry{
			{Type: "file", Path: "model.safetensors", Size: 1024},
		})
	}))
	defer hfSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))

	result, err := Copy(context.Background(), Options{
		Repo:     "Org/Model",
		Registry: "ghcr.io/test",
		Revision: "abc123",
		DryRun:   true,
		HFClient: client,
	})
	require.NoError(t, err)
	assert.Equal(t, "ghcr.io/test/org-model:rev-abc123", result.Ref)
	assert.Empty(t, result.Digest)
}

func TestCopyRegistryAuthIsPermanent(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]hf.TreeEntry{
			{Type: "file", Path: "model.safetensors", Size: 256},
		})
	}))
	defer hfSrv.Close()

	// Registry that rejects all requests with 401.
	regSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	_, err := Copy(context.Background(), Options{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.Error(t, err)
	assert.True(t, IsPermanent(err), "registry 401 should be a permanent error")
	assert.Contains(t, err.Error(), "checking registry")
}

func TestCopyHF500IsTransient(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal error"))
	}))
	defer hfSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	_, err := Copy(context.Background(), Options{
		Repo:       "Org/Model",
		Registry:   "ghcr.io/test",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.Error(t, err)
	assert.False(t, IsPermanent(err), "HF 500 should be transient (retryable)")
	assert.Contains(t, err.Error(), "listing repo")
}

func TestCopy404IsPermanent(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"error":"Repository not found"}`))
	}))
	defer hfSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	_, err := Copy(context.Background(), Options{
		Repo:       "nonexistent/repo",
		Registry:   "ghcr.io/test",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.Error(t, err)
	assert.True(t, IsPermanent(err), "404 should be a permanent error")
	assert.Contains(t, err.Error(), "not found (HTTP 404)")
}

func TestCopyMultipleWeightShards(t *testing.T) {
	const shardCount = 8
	const shardSize = 512

	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/ShardedModel/tree/main":
			entries := []hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 64},
			}
			for i := 1; i <= shardCount; i++ {
				entries = append(entries, hf.TreeEntry{
					Type: "file",
					Path: fmt.Sprintf("model-%05d-of-%05d.safetensors", i, shardCount),
					Size: shardSize,
				})
			}
			json.NewEncoder(w).Encode(entries)
		case r.URL.Path == "/Org/ShardedModel/resolve/main/config.json":
			w.Write([]byte(`{"model_type":"test"}`))
		default:
			// Serve all weight shard requests.
			w.Header().Set("Content-Length", fmt.Sprintf("%d", shardSize))
			w.Write(make([]byte, shardSize))
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	// Track progress callbacks to verify all shards are reported.
	var mu sync.Mutex
	var reportedWeights []string

	result, err := Copy(context.Background(), Options{
		Repo:       "Org/ShardedModel",
		Registry:   regHost + "/models",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
		OnUploadWeight: func(index, total int, filename string) {
			mu.Lock()
			reportedWeights = append(reportedWeights, filename)
			mu.Unlock()
		},
	})
	require.NoError(t, err)

	assert.Contains(t, result.Digest, "sha256:")
	assert.False(t, result.Cached)
	assert.Equal(t, shardCount+1, result.FileCount) // 1 config + 8 weights

	// All shards should be reported (order may vary due to parallelism).
	assert.Len(t, reportedWeights, shardCount)
	for i := 1; i <= shardCount; i++ {
		expected := fmt.Sprintf("model-%05d-of-%05d.safetensors", i, shardCount)
		assert.Contains(t, reportedWeights, expected)
	}

	// Verify pushed index has both platforms with correct layer count.
	ref, err := name.ParseReference(result.Ref)
	require.NoError(t, err)
	idx, err := remote.Index(ref)
	require.NoError(t, err)
	mf, err := idx.IndexManifest()
	require.NoError(t, err)
	assert.Len(t, mf.Manifests, 2)

	for _, d := range mf.Manifests {
		img, err := idx.Image(d.Digest)
		require.NoError(t, err)
		layers, err := img.Layers()
		require.NoError(t, err)
		assert.Len(t, layers, shardCount+1, "expected %d layers (1 config + %d weights)", shardCount+1, shardCount)
	}
}

func TestDeriveRepoName(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"NousResearch/Hermes-4.3-Llama-3-36B-AWQ", "nousresearch-hermes-4.3-llama-3-36b-awq"},
		{"Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen-qwen2.5-0.5b-instruct-gguf"},
		{"org/model", "org-model"},
	}
	for _, tt := range tests {
		assert.Equal(t, tt.want, deriveRepoName(tt.input))
	}
}

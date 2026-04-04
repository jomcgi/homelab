package copy

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/go-containerregistry/pkg/registry"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
)

func TestResolveSuccess(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/abc123":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 100},
				{Type: "file", Path: "model.safetensors", Size: 4096},
			})
		case r.URL.Path == "/api/models/Org/Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()
	regHost := regSrv.Listener.Addr().String()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "abc123",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.NoError(t, err)

	assert.Equal(t, regHost+"/models/org/model:rev-abc123", result.Ref)
	assert.False(t, result.Cached)
	assert.Empty(t, result.Digest)
	assert.Equal(t, "Org/Model", result.Repo)
	assert.Equal(t, "abc123", result.Revision)
	assert.Equal(t, FormatSafetensors, result.Format)
	assert.Equal(t, 2, result.FileCount)
	assert.Equal(t, int64(4196), result.TotalSize)
}

func TestResolveCacheHit(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/rev1":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "model.safetensors", Size: 256},
			})
		case r.URL.Path == "/api/models/Org/Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
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
	regHost := regSrv.Listener.Addr().String()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	remoteOpts := []remote.Option{}

	// Push something first via Copy.
	_, err := Copy(context.Background(), Options{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "rev1",
		HFClient:   client,
		RemoteOpts: remoteOpts,
	})
	require.NoError(t, err)

	// Now resolve should find it.
	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "rev1",
		HFClient:   client,
		RemoteOpts: remoteOpts,
	})
	require.NoError(t, err)

	assert.True(t, result.Cached)
	assert.Contains(t, result.Digest, "sha256:")
}

func TestResolveRegistryAuthTreatedAsNotFound(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "model.safetensors", Size: 256},
			})
		case r.URL.Path == "/api/models/Org/Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	// Registry that rejects all requests with 401 (GHCR behavior for nonexistent packages).
	regSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer regSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	regHost := regSrv.Listener.Addr().String()

	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:       "Org/Model",
		Registry:   regHost + "/models",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.NoError(t, err, "401 from registry should be treated as not-found, not an error")
	assert.False(t, result.Cached)
	assert.Empty(t, result.Digest)
}

func TestResolve404IsPermanent(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"error":"Repository not found"}`))
	}))
	defer hfSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	_, err := Resolve(context.Background(), ResolveOptions{
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

func TestResolveNoWeightsIsPermanent(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode([]hf.TreeEntry{
			{Type: "file", Path: "README.md", Size: 500},
			{Type: "file", Path: "config.json", Size: 100},
		})
	}))
	defer hfSrv.Close()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	_, err := Resolve(context.Background(), ResolveOptions{
		Repo:       "Org/NoWeights",
		Registry:   "ghcr.io/test",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.Error(t, err)
	assert.True(t, IsPermanent(err), "no weights should be a permanent error")
	assert.Contains(t, err.Error(), "no weight files found")
}

func TestIsMMProj(t *testing.T) {
	tests := []struct {
		path string
		want bool
	}{
		{"mmproj-BF16.gguf", true},
		{"mmproj-gemma-4-26B-A4B-it-f16.gguf", true},
		{"MMPROJ-Model-f16.gguf", true},
		{"Model-Q4_K_M.gguf", false},
		{"model.gguf", false},
	}
	for _, tt := range tests {
		assert.Equal(t, tt.want, isMMProj(tt.path), "isMMProj(%q)", tt.path)
	}
}

func TestResolveWithBaseModel(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Variant/Quantized-Model/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "model.safetensors", Size: 512},
			})
		case r.URL.Path == "/api/models/Variant/Quantized-Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{
				ID: "Variant/Quantized-Model",
				BaseModels: &hf.BaseModels{
					Relation: "quantized",
					Models:   []hf.BaseModel{{ID: "Base/Original-Model"}},
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()
	regHost := regSrv.Listener.Addr().String()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:       "Variant/Quantized-Model",
		Registry:   regHost + "/models",
		Revision:   "main",
		HFClient:   client,
		RemoteOpts: []remote.Option{},
	})
	require.NoError(t, err)

	// Derivative: repo path from base model, tag from variant name.
	assert.Equal(t, regHost+"/models/base/original-model:variant-quantized-model", result.Ref)
	assert.False(t, result.Cached)
}

func TestResolveWithMMProjIncluded(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 100},
				{Type: "file", Path: "Model-Q4_K_M.gguf", Size: 4096},
				{Type: "file", Path: "mmproj-BF16.gguf", Size: 512},
			})
		case r.URL.Path == "/api/models/Org/Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()
	regHost := regSrv.Listener.Addr().String()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:          "Org/Model",
		Registry:      regHost + "/models",
		Revision:      "main",
		File:          "Model-Q4_K_M",
		IncludeMMProj: true,
		HFClient:      client,
		RemoteOpts:    []remote.Option{},
	})
	require.NoError(t, err)

	// Tag must include -mmproj suffix when mmproj weights are selected alongside the model.
	assert.Equal(t, regHost+"/models/org/model:org-gguf-model-q4-k-m-mmproj", result.Ref)
	// config.json + Model-Q4_K_M.gguf + mmproj-BF16.gguf
	assert.Equal(t, 3, result.FileCount)
	assert.False(t, result.Cached)
}

func TestResolveWithMMProjExcluded(t *testing.T) {
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models/Org/Model/tree/main":
			json.NewEncoder(w).Encode([]hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 100},
				{Type: "file", Path: "Model-Q4_K_M.gguf", Size: 4096},
				{Type: "file", Path: "mmproj-BF16.gguf", Size: 512},
			})
		case r.URL.Path == "/api/models/Org/Model":
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hfSrv.Close()

	reg := registry.New()
	regSrv := httptest.NewServer(reg)
	defer regSrv.Close()
	regHost := regSrv.Listener.Addr().String()

	client := hf.NewClient(hf.WithBaseURL(hfSrv.URL))
	result, err := Resolve(context.Background(), ResolveOptions{
		Repo:          "Org/Model",
		Registry:      regHost + "/models",
		Revision:      "main",
		File:          "Model-Q4_K_M",
		IncludeMMProj: false,
		HFClient:      client,
		RemoteOpts:    []remote.Option{},
	})
	require.NoError(t, err)

	// Tag must NOT include -mmproj suffix when IncludeMMProj is false.
	assert.Equal(t, regHost+"/models/org/model:org-gguf-model-q4-k-m", result.Ref)
	// config.json + Model-Q4_K_M.gguf only (mmproj excluded from selection)
	assert.Equal(t, 2, result.FileCount)
	assert.False(t, result.Cached)
}

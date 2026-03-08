package ociref

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
)

func TestDeriveTag(t *testing.T) {
	tests := []struct {
		name     string
		tag      string
		revision string
		want     string
	}{
		{name: "explicit tag", tag: "latest", revision: "main", want: "latest"},
		{name: "short revision", tag: "", revision: "main", want: "rev-main"},
		{name: "long revision truncated", tag: "", revision: "abc123def456789", want: "rev-abc123def456"},
		{name: "exact 12 chars", tag: "", revision: "abc123def456", want: "rev-abc123def456"},
		{name: "empty tag empty rev", tag: "", revision: "", want: "rev-"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, DeriveTag(tt.tag, tt.revision))
		})
	}
}

func TestDeriveRepoName(t *testing.T) {
	tests := []struct {
		name string
		repo string
		want string
	}{
		{name: "mixed case", repo: "NousResearch/Hermes-3-8B", want: "nousresearch/hermes-3-8b"},
		{name: "already lowercase", repo: "org/model", want: "org/model"},
		{name: "all uppercase", repo: "ORG/MODEL", want: "org/model"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, DeriveRepoName(tt.repo))
		})
	}
}

func TestDeriveVariantTag(t *testing.T) {
	tests := []struct {
		name string
		repo string
		want string
	}{
		{name: "with slash", repo: "Emilio407/nllb-200-distilled-1.3B-4bit", want: "emilio407-nllb-200-distilled-1.3b-4bit"},
		{name: "already flat", repo: "model-name", want: "model-name"},
		{name: "uppercase", repo: "ORG/MODEL", want: "org-model"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, DeriveVariantTag(tt.repo))
		})
	}
}

func TestDeriveCompactVariantTag(t *testing.T) {
	tests := []struct {
		name          string
		author        string
		format        string
		file          string
		baseModelName string
		want          string
	}{
		{
			name:          "typical GGUF quant",
			author:        "bartowski",
			format:        "gguf",
			file:          "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
			baseModelName: "Llama-3.2-1B-Instruct",
			want:          "bartowski-gguf-q4-k-m",
		},
		{
			name:          "case insensitive prefix strip",
			author:        "bartowski",
			format:        "gguf",
			file:          "llama-3.2-1b-instruct-Q4_K_M.gguf",
			baseModelName: "Llama-3.2-1B-Instruct",
			want:          "bartowski-gguf-q4-k-m",
		},
		{
			name:          "no prefix match",
			author:        "someone",
			format:        "gguf",
			file:          "completely-different-name-Q8_0.gguf",
			baseModelName: "Llama-3.2-1B-Instruct",
			want:          "someone-gguf-completely-different-name-q8-0",
		},
		{
			name:          "empty base model name",
			author:        "bartowski",
			format:        "gguf",
			file:          "Model-Q4_K_M.gguf",
			baseModelName: "",
			want:          "bartowski-gguf-model-q4-k-m",
		},
		{
			name:          "underscore separators",
			author:        "TheBloke",
			format:        "gguf",
			file:          "Hermes-3-8B_Q5_K_S.gguf",
			baseModelName: "Hermes-3-8B",
			want:          "thebloke-gguf-q5-k-s",
		},
		{
			name:          "file selector without extension containing version dots",
			author:        "bartowski",
			format:        "gguf",
			file:          "NousResearch_Hermes-4.3-36B-IQ4_XS",
			baseModelName: "Hermes-4.3-36B",
			want:          "bartowski-gguf-nousresearch-hermes-4.3-36b-iq4-xs",
		},
		{
			name:          "file selector without extension no dots",
			author:        "bartowski",
			format:        "gguf",
			file:          "Llama-3-8B-Q4_K_M",
			baseModelName: "Llama-3-8B",
			want:          "bartowski-gguf-q4-k-m",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := DeriveCompactVariantTag(tt.author, tt.format, tt.file, tt.baseModelName)
			assert.Equal(t, tt.want, got)
		})
	}
}

func TestDeriveCompactVariantTag_Overflow(t *testing.T) {
	// A very long file name should produce a base36 hash instead of truncation.
	longFile := strings.Repeat("a", 200) + ".gguf"
	got := DeriveCompactVariantTag("author", "gguf", longFile, "")
	assert.LessOrEqual(t, len(got), 128, "overflow tag should be <= 128 chars")
	assert.Regexp(t, `^[0-9a-z]+$`, got, "base36 hash should only contain [0-9a-z]")
}

func TestDeriveFileTag(t *testing.T) {
	tests := []struct {
		name   string
		info   *hf.ModelInfo
		format string
		file   string
		want   string
	}{
		{
			name: "derivative with author and base model",
			info: &hf.ModelInfo{
				ID:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
				Author: "bartowski",
				BaseModels: &hf.BaseModels{
					Relation: "quantized",
					Models:   []hf.BaseModel{{ID: "meta-llama/Llama-3.2-1B-Instruct"}},
				},
			},
			format: "gguf",
			file:   "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
			want:   "bartowski-gguf-q4-k-m",
		},
		{
			name: "author from ID fallback",
			info: &hf.ModelInfo{
				ID: "bartowski/Model-GGUF",
			},
			format: "gguf",
			file:   "model-q4-k-m",
			want:   "bartowski-gguf-model-q4-k-m",
		},
		{
			name:   "nil info fallback to DeriveVariantTag",
			info:   nil,
			format: "gguf",
			file:   "model-q4-k-m",
			want:   "model-q4-k-m",
		},
		{
			name:   "empty author fallback",
			info:   &hf.ModelInfo{ID: "model"},
			format: "gguf",
			file:   "model-q4-k-m",
			want:   "model-q4-k-m",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := DeriveFileTag(tt.info, tt.format, tt.file)
			assert.Equal(t, tt.want, got)
		})
	}
}

func TestResolveRef_BaseModel(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/NousResearch/Hermes-3-8B" {
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "NousResearch/Hermes-3-8B"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "NousResearch/Hermes-3-8B", "ghcr.io/jomcgi/models", "")
	assert.Equal(t, "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main", ref)
}

func TestResolveRef_DerivativeModel(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/Emilio407/nllb-200-distilled-1.3B-4bit" {
			json.NewEncoder(w).Encode(hf.ModelInfo{
				ID:     "Emilio407/nllb-200-distilled-1.3B-4bit",
				Author: "Emilio407",
				BaseModels: &hf.BaseModels{
					Relation: "quantized",
					Models:   []hf.BaseModel{{ID: "facebook/nllb-200-distilled-1.3B"}},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "Emilio407/nllb-200-distilled-1.3B-4bit", "ghcr.io/jomcgi/models", "")
	assert.Equal(t, "ghcr.io/jomcgi/models/facebook/nllb-200-distilled-1.3b:emilio407-nllb-200-distilled-1.3b-4bit", ref)
}

func TestResolveRef_HFFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "Org/Model", "ghcr.io/test", "")
	// Falls back to simple naming (no file selector = rev-main)
	assert.Equal(t, "ghcr.io/test/org/model:rev-main", ref)
}

func TestResolveRef_NoFile(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "Org/Model", "ghcr.io/test", "")
	assert.Equal(t, "ghcr.io/test/org/model:rev-main", ref)
}

func TestResolveRef_WithFileSelector(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(hf.ModelInfo{ID: "bartowski/Model-GGUF"})
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "bartowski/Model-GGUF", "ghcr.io/test", "model-q4-k-m")
	// Base model with file: author from ID, no base model to strip prefix, format=gguf.
	assert.Equal(t, "ghcr.io/test/bartowski/model-gguf:bartowski-gguf-model-q4-k-m", ref)
}

func TestResolveRef_DerivativeWithFileSelector(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(hf.ModelInfo{
			ID:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			Author: "bartowski",
			BaseModels: &hf.BaseModels{
				Relation: "quantized",
				Models:   []hf.BaseModel{{ID: "meta-llama/Llama-3.2-1B-Instruct"}},
			},
		})
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "bartowski/Llama-3.2-1B-Instruct-GGUF", "ghcr.io/jomcgi/models", "Llama-3.2-1B-Instruct-Q4_K_M")
	// Derivative + file: compact tag strips base model name prefix.
	assert.Equal(t, "ghcr.io/jomcgi/models/meta-llama/llama-3.2-1b-instruct:bartowski-gguf-q4-k-m", ref)
}

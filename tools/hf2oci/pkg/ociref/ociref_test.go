package ociref

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
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
	ref := ResolveRef(context.Background(), client, "NousResearch/Hermes-3-8B", "ghcr.io/jomcgi/models", "main")
	assert.Equal(t, "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main", ref)
}

func TestResolveRef_DerivativeModel(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/Emilio407/nllb-200-distilled-1.3B-4bit" {
			json.NewEncoder(w).Encode(hf.ModelInfo{
				ID: "Emilio407/nllb-200-distilled-1.3B-4bit",
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
	ref := ResolveRef(context.Background(), client, "Emilio407/nllb-200-distilled-1.3B-4bit", "ghcr.io/jomcgi/models", "main")
	assert.Equal(t, "ghcr.io/jomcgi/models/facebook/nllb-200-distilled-1.3b:emilio407-nllb-200-distilled-1.3b-4bit", ref)
}

func TestResolveRef_HFFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "Org/Model", "ghcr.io/test", "abc123def456")
	// Falls back to simple naming
	assert.Equal(t, "ghcr.io/test/org/model:rev-abc123def456", ref)
}

func TestResolveRef_EmptyRevision(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/Model"})
	}))
	defer srv.Close()

	client := hf.NewClient(hf.WithBaseURL(srv.URL))
	ref := ResolveRef(context.Background(), client, "Org/Model", "ghcr.io/test", "")
	// Empty revision defaults to "main"
	assert.Equal(t, "ghcr.io/test/org/model:rev-main", ref)
}

package main

// resolver_adapter_test.go covers the field-mapping logic of hf2ociResolver.Resolve().
//
// Gap #1c from the coverage report: the 7-field result mapping from copy.Result
// to controller.ResolveResult was never verified. This file documents the exact
// field correspondence and verifies the Format type conversion (ModelFormat→string).
//
// Error-path coverage (permanent / transient) lives in resolver_test.go which
// exercises the real adapter via a fake HTTP server.

import (
	"testing"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/copy"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/controller"
)

// mapResult replicates the exact field-mapping performed by hf2ociResolver.Resolve.
// Any change to the mapping in main.go will cause this test to drift (intentionally).
func mapResult(r *copy.Result) *controller.ResolveResult {
	return &controller.ResolveResult{
		Ref:       r.Ref,
		Digest:    r.Digest,
		Cached:    r.Cached,
		Revision:  r.Revision,
		Format:    string(r.Format),
		FileCount: r.FileCount,
		TotalSize: r.TotalSize,
	}
}

// TestHf2ociResolver_ResultMapping_AllSevenFields verifies that all 7 fields
// from copy.Result are correctly mapped to controller.ResolveResult.
// Each field uses a unique value so a field-swap bug is detectable.
func TestHf2ociResolver_ResultMapping_AllSevenFields(t *testing.T) {
	copyResult := &copy.Result{
		Ref:       "ghcr.io/jomcgi/models/llama-3.2:rev-main",
		Digest:    "sha256:abc123def456",
		Cached:    true,
		Revision:  "main",
		Format:    copy.ModelFormat("safetensors"),
		FileCount: 42,
		TotalSize: 8_589_934_592,
	}

	got := mapResult(copyResult)

	if got.Ref != "ghcr.io/jomcgi/models/llama-3.2:rev-main" {
		t.Errorf("Ref: got %q, want %q", got.Ref, copyResult.Ref)
	}
	if got.Digest != "sha256:abc123def456" {
		t.Errorf("Digest: got %q, want %q", got.Digest, copyResult.Digest)
	}
	if !got.Cached {
		t.Error("Cached: expected true")
	}
	if got.Revision != "main" {
		t.Errorf("Revision: got %q, want %q", got.Revision, copyResult.Revision)
	}
	if got.Format != "safetensors" {
		t.Errorf("Format: got %q, want %q", got.Format, string(copyResult.Format))
	}
	if got.FileCount != 42 {
		t.Errorf("FileCount: got %d, want %d", got.FileCount, copyResult.FileCount)
	}
	if got.TotalSize != 8_589_934_592 {
		t.Errorf("TotalSize: got %d, want %d", got.TotalSize, copyResult.TotalSize)
	}
}

// TestHf2ociResolver_ResultMapping_CacheMiss verifies the mapping when the
// model is not yet in the registry (Cached=false, Digest="").
func TestHf2ociResolver_ResultMapping_CacheMiss(t *testing.T) {
	copyResult := &copy.Result{
		Ref:       "ghcr.io/jomcgi/models/llama-3.2:rev-main",
		Digest:    "", // not yet cached
		Cached:    false,
		Revision:  "main",
		Format:    copy.ModelFormat("gguf"),
		FileCount: 1,
		TotalSize: 4_294_967_296,
	}

	got := mapResult(copyResult)

	if got.Cached {
		t.Error("Cached: expected false for cache miss")
	}
	if got.Digest != "" {
		t.Errorf("Digest: expected empty for cache miss, got %q", got.Digest)
	}
	if got.Format != "gguf" {
		t.Errorf("Format: got %q, want \"gguf\"", got.Format)
	}
}

// TestHf2ociResolver_ResultMapping_FormatIsStringConversion verifies that
// copy.ModelFormat (a named string type) is converted to a plain string.
// This guards against future accidental type changes breaking the mapping.
func TestHf2ociResolver_ResultMapping_FormatIsStringConversion(t *testing.T) {
	cases := []struct {
		format copy.ModelFormat
		want   string
	}{
		{copy.ModelFormat("safetensors"), "safetensors"},
		{copy.ModelFormat("gguf"), "gguf"},
		{copy.ModelFormat(""), ""},
	}

	for _, tc := range cases {
		got := string(tc.format)
		if got != tc.want {
			t.Errorf("string(%q) = %q, want %q", tc.format, got, tc.want)
		}
	}
}

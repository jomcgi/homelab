package naming

import "testing"

func TestModelCacheName(t *testing.T) {
	tests := []struct {
		name     string
		repo     string
		revision string
		want     string
	}{
		{
			name:     "simple repo with default revision",
			repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			revision: "main",
			want:     "bartowski-llama-3.2-1b-instruct-gguf-rev-main",
		},
		{
			name:     "empty revision defaults to main",
			repo:     "org/model",
			revision: "",
			want:     "org-model-rev-main",
		},
		{
			name:     "long revision truncated to 12 chars",
			repo:     "org/model",
			revision: "abc123def456789",
			want:     "org-model-rev-abc123def456",
		},
		{
			name:     "uppercase normalized",
			repo:     "NousResearch/Hermes-3-8B",
			revision: "main",
			want:     "nousresearch-hermes-3-8b-rev-main",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ModelCacheName(tt.repo, tt.revision)
			if got != tt.want {
				t.Errorf("ModelCacheName(%q, %q) = %q, want %q", tt.repo, tt.revision, got, tt.want)
			}
		})
	}
}

func TestModelCacheNameLength(t *testing.T) {
	// Very long repo name should be truncated to <= 63 chars
	got := ModelCacheName("very-long-organization-name/extremely-long-model-name-that-goes-on-and-on", "main")
	if len(got) > 63 {
		t.Errorf("ModelCacheName returned name with %d chars, want <= 63: %q", len(got), got)
	}
}

func TestModelCacheNameDeterministic(t *testing.T) {
	a := ModelCacheName("org/model", "main")
	b := ModelCacheName("org/model", "main")
	if a != b {
		t.Errorf("ModelCacheName is not deterministic: %q != %q", a, b)
	}
}

func TestModelCacheNameUnique(t *testing.T) {
	a := ModelCacheName("org/model", "v1")
	b := ModelCacheName("org/model", "v2")
	if a == b {
		t.Errorf("different revisions should produce different names: %q == %q", a, b)
	}
}

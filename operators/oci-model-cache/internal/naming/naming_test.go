package naming

import "testing"

func TestModelCacheName(t *testing.T) {
	tests := []struct {
		name string
		repo string
		file string
		want string
	}{
		{
			name: "simple repo no file",
			repo: "bartowski/Llama-3.2-1B-Instruct-GGUF",
			file: "",
			want: "bartowski-llama-3.2-1b-instruct-gguf",
		},
		{
			name: "repo with file selector",
			repo: "bartowski/NousResearch_Hermes-4-14B-GGUF",
			file: "NousResearch_Hermes-4-14B-IQ4_XS",
			want: "bartowski-nousresearch-hermes-4-14b-gguf-nousresearch-hermes-4-14b-iq4-xs",
		},
		{
			name: "uppercase normalized",
			repo: "NousResearch/Hermes-3-8B",
			file: "",
			want: "nousresearch-hermes-3-8b",
		},
		{
			name: "safetensors model",
			repo: "Emilio407/nllb-200-distilled-1.3B-4bit",
			file: "",
			want: "emilio407-nllb-200-distilled-1.3b-4bit",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ModelCacheName(tt.repo, tt.file)
			if len(tt.want) <= 63 {
				if got != tt.want {
					t.Errorf("ModelCacheName(%q, %q) = %q, want %q", tt.repo, tt.file, got, tt.want)
				}
			}
			if len(got) > 63 {
				t.Errorf("ModelCacheName(%q, %q) = %q (%d chars), want <= 63", tt.repo, tt.file, got, len(got))
			}
		})
	}
}

func TestModelCacheNameLength(t *testing.T) {
	// Very long repo + file should be truncated to <= 63 chars
	got := ModelCacheName("very-long-organization-name/extremely-long-model-name-that-goes-on-and-on", "SomeLongFileName")
	if len(got) > 63 {
		t.Errorf("ModelCacheName returned name with %d chars, want <= 63: %q", len(got), got)
	}
}

func TestModelCacheNameDeterministic(t *testing.T) {
	a := ModelCacheName("org/model", "")
	b := ModelCacheName("org/model", "")
	if a != b {
		t.Errorf("ModelCacheName is not deterministic: %q != %q", a, b)
	}
}

func TestModelCacheNameUnique(t *testing.T) {
	a := ModelCacheName("org/model-GGUF", "model-Q4_K_M")
	b := ModelCacheName("org/model-GGUF", "model-Q8_0")
	if a == b {
		t.Errorf("different files should produce different names: %q == %q", a, b)
	}
}

package hfref

import "testing"

func TestParse(t *testing.T) {
	tests := []struct {
		name         string
		volumeName   string
		wantRepo     string
		wantRevision string
		wantOK       bool
	}{
		{
			name:         "simple hf ref",
			volumeName:   "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF",
			wantRepo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			wantRevision: "main",
			wantOK:       true,
		},
		{
			name:         "hf ref with revision",
			volumeName:   "hf.co/NousResearch/Hermes-3-8B@abc123def",
			wantRepo:     "NousResearch/Hermes-3-8B",
			wantRevision: "abc123def",
			wantOK:       true,
		},
		{
			name:         "not an hf ref",
			volumeName:   "ghcr.io/some/image:tag",
			wantRepo:     "",
			wantRevision: "",
			wantOK:       false,
		},
		{
			name:         "hf.co with no org/model",
			volumeName:   "hf.co/justmodel",
			wantRepo:     "",
			wantRevision: "",
			wantOK:       false,
		},
		{
			name:         "empty after prefix",
			volumeName:   "hf.co/",
			wantRepo:     "",
			wantRevision: "",
			wantOK:       false,
		},
		{
			name:         "empty string",
			volumeName:   "",
			wantRepo:     "",
			wantRevision: "",
			wantOK:       false,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			repo, revision, ok := Parse(tt.volumeName)
			if ok != tt.wantOK {
				t.Errorf("Parse(%q) ok = %v, want %v", tt.volumeName, ok, tt.wantOK)
			}
			if repo != tt.wantRepo {
				t.Errorf("Parse(%q) repo = %q, want %q", tt.volumeName, repo, tt.wantRepo)
			}
			if revision != tt.wantRevision {
				t.Errorf("Parse(%q) revision = %q, want %q", tt.volumeName, revision, tt.wantRevision)
			}
		})
	}
}

func TestIsHFRef(t *testing.T) {
	if !IsHFRef("hf.co/org/model") {
		t.Error("expected hf.co/org/model to be an HF ref")
	}
	if IsHFRef("ghcr.io/org/image") {
		t.Error("expected ghcr.io/org/image to not be an HF ref")
	}
}

package copy

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
)

func TestClassify(t *testing.T) {
	tests := []struct {
		name        string
		entries     []hf.TreeEntry
		wantConfigs int
		wantWeights int
		wantFormat  ModelFormat
		wantErr     string
	}{
		{
			name: "safetensors model with configs",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 1000},
				{Type: "file", Path: "tokenizer.json", Size: 2000},
				{Type: "file", Path: "tokenizer_config.json", Size: 500},
				{Type: "file", Path: "model.safetensors.index.json", Size: 300},
				{Type: "file", Path: "model-00001-of-00002.safetensors", Size: 5000000000},
				{Type: "file", Path: "model-00002-of-00002.safetensors", Size: 3000000000},
				{Type: "file", Path: "README.md", Size: 100},
				{Type: "file", Path: ".gitattributes", Size: 50},
			},
			wantConfigs: 4,
			wantWeights: 2,
			wantFormat:  FormatSafetensors,
		},
		{
			name: "single GGUF file",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "model-q4_k_m.gguf", Size: 4000000000},
				{Type: "file", Path: "README.md", Size: 100},
			},
			wantConfigs: 0,
			wantWeights: 1,
			wantFormat:  FormatGGUF,
		},
		{
			name: "mixed formats error",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "model.safetensors", Size: 5000000000},
				{Type: "file", Path: "model.gguf", Size: 4000000000},
			},
			wantErr: "mixed model formats",
		},
		{
			name: "no weight files error",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 1000},
				{Type: "file", Path: "README.md", Size: 100},
			},
			wantErr: "no weight files found",
		},
		{
			name: "index.json is config not weight",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "model.safetensors.index.json", Size: 300},
				{Type: "file", Path: "model.safetensors", Size: 5000000000},
			},
			wantConfigs: 1,
			wantWeights: 1,
			wantFormat:  FormatSafetensors,
		},
		{
			name: "directories are ignored",
			entries: []hf.TreeEntry{
				{Type: "directory", Path: "subfolder"},
				{Type: "file", Path: "model.gguf", Size: 4000000000},
			},
			wantConfigs: 0,
			wantWeights: 1,
			wantFormat:  FormatGGUF,
		},
		{
			name: "generation_config as config",
			entries: []hf.TreeEntry{
				{Type: "file", Path: "config.json", Size: 1000},
				{Type: "file", Path: "generation_config.json", Size: 200},
				{Type: "file", Path: "special_tokens_map.json", Size: 100},
				{Type: "file", Path: "vocab.txt", Size: 3000},
				{Type: "file", Path: "merges.txt", Size: 2000},
				{Type: "file", Path: "model.safetensors", Size: 5000000000},
			},
			wantConfigs: 5,
			wantWeights: 1,
			wantFormat:  FormatSafetensors,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			configs, weights, format, err := Classify(tt.entries)
			if tt.wantErr != "" {
				require.Error(t, err)
				assert.Contains(t, err.Error(), tt.wantErr)
				return
			}
			require.NoError(t, err)
			assert.Len(t, configs, tt.wantConfigs)
			assert.Len(t, weights, tt.wantWeights)
			assert.Equal(t, tt.wantFormat, format)
		})
	}
}

package copy

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

// ModelFormat represents the format of model weight files.
type ModelFormat string

const (
	FormatSafetensors ModelFormat = "safetensors"
	FormatGGUF        ModelFormat = "gguf"
)

// configFiles are files classified as config (small metadata/tokenizer files).
var configFiles = map[string]bool{
	"config.json":                    true,
	"tokenizer.json":                 true,
	"tokenizer_config.json":          true,
	"generation_config.json":         true,
	"special_tokens_map.json":        true,
	"model.safetensors.index.json":   true,
	"vocab.txt":                      true,
	"merges.txt":                     true,
	"preprocessor_config.json":       true,
	"chat_template.json":             true,
	"added_tokens.json":              true,
	"quantize_config.json":           true,
	"quant_config.json":              true,
	"tokenizer_config.json.template": true,
}

// Classify separates HuggingFace tree entries into config files, weight files,
// and detects the model format. Files that don't match config or weight patterns
// are silently ignored (README.md, LICENSE, .gitattributes, etc.).
func Classify(entries []hf.TreeEntry) (configs []hf.TreeEntry, weights []hf.TreeEntry, format ModelFormat, err error) {
	var hasSafetensors, hasGGUF bool

	for _, e := range entries {
		if e.Type != "file" {
			continue
		}

		base := filepath.Base(e.Path)

		if configFiles[base] {
			configs = append(configs, e)
			continue
		}

		ext := strings.ToLower(filepath.Ext(base))
		switch ext {
		case ".safetensors":
			weights = append(weights, e)
			hasSafetensors = true
		case ".gguf":
			weights = append(weights, e)
			hasGGUF = true
		}
		// Everything else (README.md, LICENSE, .gitattributes, etc.) is ignored.
	}

	if hasSafetensors && hasGGUF {
		return nil, nil, "", fmt.Errorf("mixed model formats: found both .safetensors and .gguf files")
	}
	if !hasSafetensors && !hasGGUF {
		return nil, nil, "", fmt.Errorf("no weight files found (expected .safetensors or .gguf)")
	}

	if hasSafetensors {
		format = FormatSafetensors
	} else {
		format = FormatGGUF
	}

	return configs, weights, format, nil
}

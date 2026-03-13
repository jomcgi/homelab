package main

import (
	"fmt"

	"gopkg.in/yaml.v3"
)

// renderRecipeYAML marshals a recipe map to YAML for writing to a temp file.
//
// The recipe is marshaled as-is — template variables like {{ task_description }}
// are preserved so that goose's MiniJinja engine can substitute them at runtime
// via `goose run --recipe <file> --params task_description=<value>`.
//
// Earlier versions pre-substituted template variables in Go, but this caused a
// cascade of bugs: YAML-special characters in tasks broke quoting, indent
// filters produced explicit indent indicators (|4) that serde_yaml rejected,
// and orphaned parameter declarations triggered "Unnecessary parameter
// definitions" errors from goose's recipe validator.
func renderRecipeYAML(recipe map[string]any) (string, error) {
	raw, err := yaml.Marshal(recipe)
	if err != nil {
		return "", fmt.Errorf("marshaling recipe: %w", err)
	}
	return string(raw), nil
}

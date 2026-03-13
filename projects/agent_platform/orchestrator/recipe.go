package main

import (
	"fmt"
	"regexp"

	"gopkg.in/yaml.v3"
)

// templateVarRe matches {{ task_description }} with or without an indent filter.
// The indent filter (e.g. {{ task_description | indent(2) }}) is a MiniJinja
// directive — it is meaningful only when goose's own template engine renders
// the recipe. Since the orchestrator pre-substitutes the variable before
// handing the recipe to goose, the indent filter is stripped: yaml.Marshal
// handles block-scalar indentation correctly on its own.
var templateVarRe = regexp.MustCompile(`\{\{\s*task_description\s*(?:\|[^}]*)?\}\}`)

// renderRecipeYAML takes a recipe map, substitutes {{ task_description }}
// template variables with the given task, and returns the rendered YAML string.
//
// Substitution happens at the map level (before yaml.Marshal) so that
// yaml.Marshal sees the final string content and chooses correct quoting.
// Doing it post-marshal broke in two ways:
//  1. YAML-special characters in the task (apostrophes, colons) inherited
//     incompatible quoting from the template variable placeholder.
//  2. The indent(N) filter added leading spaces that caused yaml.Marshal
//     to emit explicit indent indicators (e.g. |4) which serde_yaml in
//     goose rejected with "did not find expected key".
func renderRecipeYAML(recipe map[string]any, task string) (string, error) {
	rendered := substituteVars(recipe, task)
	raw, err := yaml.Marshal(rendered)
	if err != nil {
		return "", fmt.Errorf("marshaling recipe: %w", err)
	}
	return string(raw), nil
}

// substituteVars recursively walks a value tree and replaces template
// variables in string values with the task content.
func substituteVars(v any, task string) any {
	switch val := v.(type) {
	case map[string]any:
		out := make(map[string]any, len(val))
		for k, child := range val {
			out[k] = substituteVars(child, task)
		}
		return out
	case []any:
		out := make([]any, len(val))
		for i, child := range val {
			out[i] = substituteVars(child, task)
		}
		return out
	case string:
		return templateVarRe.ReplaceAllString(val, task)
	default:
		return v
	}
}

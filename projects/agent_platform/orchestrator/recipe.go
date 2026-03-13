package main

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

// indentRe matches {{ task_description | indent(N) }}.
var indentRe = regexp.MustCompile(`\{\{\s*task_description\s*\|\s*indent\((\d+)\)\s*\}\}`)

// renderRecipeYAML takes a recipe map, substitutes {{ task_description }}
// template variables with the given task, and returns the rendered YAML string.
//
// Substitution happens at the map level (before yaml.Marshal) so that
// yaml.Marshal sees the final string content and chooses correct quoting.
// The previous approach — marshal first, then regex-replace on the raw YAML —
// broke when task descriptions contained YAML-special characters (apostrophes,
// colons, etc.) because the quoting style chosen for the template variable
// string was incompatible with the substituted content.
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
		return replaceTemplateVars(val, task)
	default:
		return v
	}
}

// replaceTemplateVars substitutes template variables in a single string.
func replaceTemplateVars(s, task string) string {
	// Replace {{ task_description | indent(N) }} first (more specific).
	s = indentRe.ReplaceAllStringFunc(s, func(match string) string {
		sub := indentRe.FindStringSubmatch(match)
		n, _ := strconv.Atoi(sub[1])
		prefix := strings.Repeat(" ", n)
		lines := strings.Split(task, "\n")
		for i := range lines {
			lines[i] = prefix + lines[i]
		}
		return strings.Join(lines, "\n")
	})

	// Replace plain {{ task_description }}.
	s = strings.ReplaceAll(s, "{{ task_description }}", task)

	return s
}

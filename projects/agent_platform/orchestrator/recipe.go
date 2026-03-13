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
func renderRecipeYAML(recipe map[string]any, task string) (string, error) {
	raw, err := yaml.Marshal(recipe)
	if err != nil {
		return "", fmt.Errorf("marshaling recipe: %w", err)
	}
	s := string(raw)

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

	return s, nil
}

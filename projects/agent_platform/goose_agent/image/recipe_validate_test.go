// Package image_test validates that Goose recipe YAML files are well-formed and
// use safe template patterns. Run via `bazel test //projects/agent_platform/goose_agent/image:recipe_validate_test`.
package image_test

import (
	_ "embed"
	"fmt"
	"regexp"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

//go:embed recipes/code-fix.yaml
var codeFix []byte

//go:embed recipes/ci-debug.yaml
var ciDebug []byte

//go:embed recipes/research.yaml
var research []byte

//go:embed recipes/bazel.yaml
var bazel []byte

// recipeFile mirrors the fields we care about for validation.
type recipeFile struct {
	Version      string `yaml:"version"`
	Title        string `yaml:"title"`
	Description  string `yaml:"description"`
	Instructions string `yaml:"instructions"`
	Prompt       string `yaml:"prompt"`
	Parameters   []struct {
		Key         string `yaml:"key"`
		Description string `yaml:"description"`
		InputType   string `yaml:"input_type"`
		Requirement string `yaml:"requirement"`
	} `yaml:"parameters"`
}

// templateVarRe extracts Jinja2-style {{ variable }} identifiers, with or
// without filters (e.g. {{ var }}, {{ var | indent(2) }}).
var templateVarRe = regexp.MustCompile(`\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|[^}]*)?\}\}`)

// unsafePromptRe matches `prompt: "{{ ... }}"` — an inline double-quoted
// YAML scalar containing a template variable. This format is unsafe because
// task descriptions containing double quotes will corrupt the YAML after
// rendering and cause serde_yaml parse errors ("did not find expected key",
// "found unexpected document indicator").
var unsafePromptRe = regexp.MustCompile(`(?m)^\s*prompt:\s*"[^"]*\{\{[^"]*`)

// bareTemplateVarInBlockRe matches an indented line that contains only a bare
// template variable like `  {{ task_description }}` without an indent filter.
// Inside a YAML block scalar (prompt: |), MiniJinja substitutes the variable
// literally. Multi-line values break out of the block scalar because subsequent
// lines lack indentation, producing multi-document YAML that serde_yaml rejects.
// The fix is to use the indent filter: `{{ var | indent(2) }}`.
var bareTemplateVarInBlockRe = regexp.MustCompile(`(?m)^\s+\{\{\s*[a-zA-Z_]\w*\s*\}\}\s*$`)

func TestRecipeYAML(t *testing.T) {
	cases := []struct {
		name string
		raw  []byte
	}{
		{"code-fix", codeFix},
		{"ci-debug", ciDebug},
		{"research", research},
		{"bazel", bazel},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var r recipeFile
			if err := yaml.Unmarshal(tc.raw, &r); err != nil {
				t.Fatalf("recipe %s: failed to parse YAML: %v", tc.name, err)
			}

			// --- required fields ---
			if strings.TrimSpace(r.Title) == "" {
				t.Errorf("recipe %s: missing required field 'title'", tc.name)
			}
			if strings.TrimSpace(r.Description) == "" {
				t.Errorf("recipe %s: missing required field 'description'", tc.name)
			}
			if strings.TrimSpace(r.Instructions) == "" && strings.TrimSpace(r.Prompt) == "" {
				t.Errorf("recipe %s: must have at least one of 'instructions' or 'prompt'", tc.name)
			}

			// --- prompt must use block scalar when it contains template variables ---
			// Inline double-quoted scalars with {{ variable }} break YAML after
			// rendering if the substituted value contains double quotes.
			if unsafePromptRe.Match(tc.raw) {
				t.Errorf(
					"recipe %s: prompt field uses unsafe inline double-quoted format "+
						"containing a template variable (e.g. prompt: \"{{ var }}\"). "+
						"Use block scalar format instead:\n  prompt: |\n    {{ var }}",
					tc.name,
				)
			}

			// --- block scalar template variables must use indent filter ---
			// A bare {{ var }} inside a block scalar produces multi-document
			// YAML when the substituted value is multi-line, because MiniJinja
			// doesn't auto-indent subsequent lines.
			if matches := bareTemplateVarInBlockRe.FindAll(tc.raw, -1); len(matches) > 0 {
				for _, m := range matches {
					t.Errorf(
						"recipe %s: bare template variable %q in block scalar will break "+
							"YAML when the value is multi-line. Use the indent filter:\n"+
							"  {{ var | indent(2) }}",
						tc.name, strings.TrimSpace(string(m)),
					)
				}
			}

			// --- parameter definitions ---
			for i, p := range r.Parameters {
				loc := fmt.Sprintf("recipe %s parameter[%d]", tc.name, i)
				if strings.TrimSpace(p.Key) == "" {
					t.Errorf("%s: missing 'key'", loc)
				}
				if strings.TrimSpace(p.Description) == "" {
					t.Errorf("%s: missing 'description'", loc)
				}
				if strings.TrimSpace(p.InputType) == "" {
					t.Errorf("%s: missing 'input_type'", loc)
				}
				if strings.TrimSpace(p.Requirement) == "" {
					t.Errorf("%s: missing 'requirement'", loc)
				}
			}

			// --- template variables in prompt/instructions must be declared as parameters ---
			paramKeys := make(map[string]bool)
			for _, p := range r.Parameters {
				paramKeys[p.Key] = true
			}
			for _, text := range []string{r.Prompt, r.Instructions} {
				for _, m := range templateVarRe.FindAllStringSubmatch(text, -1) {
					key := m[1]
					if !paramKeys[key] {
						t.Errorf(
							"recipe %s: template variable '{{ %s }}' used but not declared in parameters",
							tc.name, key,
						)
					}
				}
			}
		})
	}
}

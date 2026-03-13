package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRenderRecipe_SimpleSubstitution(t *testing.T) {
	recipe := map[string]any{
		"prompt": "{{ task_description }}",
	}
	rendered, err := renderRecipeYAML(recipe, "fix the build")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(rendered, "fix the build") {
		t.Fatalf("expected rendered recipe to contain task, got:\n%s", rendered)
	}
	if strings.Contains(rendered, "{{ task_description }}") {
		t.Fatal("template variable was not replaced")
	}
}

func TestRenderRecipe_IndentFilter(t *testing.T) {
	recipe := map[string]any{
		"prompt": "{{ task_description | indent(2) }}",
	}
	rendered, err := renderRecipeYAML(recipe, "line1\nline2")
	if err != nil {
		t.Fatal(err)
	}

	// Parse the rendered YAML and verify the prompt value has indented lines.
	var parsed map[string]any
	if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
		t.Fatalf("rendered YAML is invalid:\n%s\nparse error: %v", rendered, err)
	}
	prompt, _ := parsed["prompt"].(string)
	if !strings.Contains(prompt, "  line1\n  line2") {
		t.Fatalf("expected indented lines in prompt value, got:\n%s", prompt)
	}
}

func TestRenderRecipe_RenderedYAMLIsValid(t *testing.T) {
	recipe := map[string]any{
		"version":      "1.0.0",
		"title":        "Test Recipe",
		"description":  "A test recipe",
		"instructions": "Do the thing",
		"prompt":       "{{ task_description | indent(2) }}",
		"parameters": []any{
			map[string]any{
				"key":         "task_description",
				"description": "The task",
				"input_type":  "string",
				"requirement": "required",
			},
		},
	}

	rendered, err := renderRecipeYAML(recipe, "fix the bug in api.go")
	if err != nil {
		t.Fatal(err)
	}

	var parsed map[string]any
	if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
		t.Fatalf("rendered YAML is not valid:\n%s\nparse error: %v", rendered, err)
	}
}

// TestRenderRecipe_YAMLHostileTask verifies that task descriptions containing
// characters that are special in YAML don't corrupt the rendered recipe.
// This is the root cause of the "did not find expected key" error from goose.
func TestRenderRecipe_YAMLHostileTask(t *testing.T) {
	recipe := map[string]any{
		"version":      "1.0.0",
		"title":        "Test",
		"description":  "Test recipe",
		"instructions": "Do the thing",
		"prompt":       "{{ task_description | indent(2) }}",
		"parameters": []any{
			map[string]any{
				"key":         "task_description",
				"description": "The task",
				"input_type":  "string",
				"requirement": "required",
			},
		},
	}

	hostileTasks := []struct {
		name string
		task string
	}{
		{
			"double_quotes",
			`Fix the "authentication" bug in the "login" handler`,
		},
		{
			"single_quotes",
			`Don't break the parser's ability to handle apostrophes`,
		},
		{
			"colons",
			"Fix config: update key: value pairs in settings: section",
		},
		{
			"yaml_document_separator",
			"First part\n---\nSecond part after separator",
		},
		{
			"yaml_end_marker",
			"Some task\n...\nMore text",
		},
		{
			"curly_braces",
			`Fix the template: {{ not_a_var }} and {key: value}`,
		},
		{
			"multiline_with_special_chars",
			"Review files changed in commits abc..def on main.\nFor each Go or Python source file:\n- Check `gh pr list --search \"test\"`\n- Skip files in generated code (zz_generated.*, *_types.go deepcopy)\nCreate one PR per project. Use conventional commit format: test(<project>): add coverage",
		},
		{
			"hash_comments",
			"Fix the bug # this is not a comment\n# but this line starts with hash",
		},
		{
			"square_brackets",
			"Update [array] values and fix [nested [brackets]]",
		},
		{
			"ampersand_and_asterisk",
			"Fix &anchor and *alias references in YAML config",
		},
		{
			"percent_and_at",
			"Check %TAG and @annotation handling",
		},
		{
			"pipe_and_gt",
			"Use | for block scalar and > for folded scalar",
		},
		{
			"backticks_with_code",
			"Run `bazel test //...` and check `go test -v ./...` output",
		},
	}

	for _, tc := range hostileTasks {
		t.Run(tc.name, func(t *testing.T) {
			rendered, err := renderRecipeYAML(recipe, tc.task)
			if err != nil {
				t.Fatalf("renderRecipeYAML failed: %v", err)
			}

			var parsed map[string]any
			if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
				t.Fatalf("rendered YAML is not parseable:\n%s\nparse error: %v", rendered, err)
			}

			// Verify the prompt field contains the task text.
			prompt, ok := parsed["prompt"].(string)
			if !ok {
				t.Fatalf("prompt field missing or not a string in parsed YAML")
			}
			// After indentation, lines get prefixed with spaces, so check
			// that at least the first line of the task appears.
			firstLine := strings.SplitN(tc.task, "\n", 2)[0]
			if !strings.Contains(prompt, strings.TrimSpace(firstLine)) {
				t.Errorf("prompt doesn't contain first line of task %q:\n%s", firstLine, prompt)
			}
		})
	}
}

// TestRenderRecipe_JSONRoundtrip simulates the Helm values → ConfigMap JSON →
// Go map[string]any → renderRecipeYAML path that recipes take in production.
// The JSON roundtrip can lose YAML block scalar formatting, so this test
// verifies the rendered YAML is still valid after that transformation.
func TestRenderRecipe_JSONRoundtrip(t *testing.T) {
	original := map[string]any{
		"version":     "1.0.0",
		"title":       "Code Fix",
		"description": "Fix code issues",
		"instructions": "Fix the described issue.\n" +
			"Run bazel test //... to verify.\n" +
			"Commit using conventional commits.\n\n" +
			"## Output Format\n" +
			"```goose-result\ntype: pr | issue\nurl: <URL>\n```\n",
		"prompt": "{{ task_description | indent(2) }}",
		"parameters": []any{
			map[string]any{
				"key":         "task_description",
				"description": "The task to perform",
				"input_type":  "string",
				"requirement": "required",
			},
		},
		"extensions": []any{
			map[string]any{"type": "builtin", "name": "developer"},
		},
		"settings": map[string]any{
			"max_turns":            50,
			"max_tool_repetitions": 5,
		},
	}

	// Simulate JSON roundtrip (Helm toJson → Go json.Unmarshal).
	jsonBytes, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	var roundtripped map[string]any
	if err := json.Unmarshal(jsonBytes, &roundtripped); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	task := "Review files changed in commits abc..def.\n" +
		"For each Go file: check `gh pr list --search \"test\"`\n" +
		"Create one PR per project. Format: test(<project>): add coverage"

	rendered, err := renderRecipeYAML(roundtripped, task)
	if err != nil {
		t.Fatalf("renderRecipeYAML: %v", err)
	}

	var parsed map[string]any
	if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
		t.Fatalf("rendered YAML is not valid after JSON roundtrip:\n%s\nparse error: %v", rendered, err)
	}

	if parsed["title"] != "Code Fix" {
		t.Errorf("title mismatch: got %v", parsed["title"])
	}
	if parsed["version"] != "1.0.0" {
		t.Errorf("version mismatch: got %v", parsed["version"])
	}
}

// TestRenderRecipe_RealRecipeFiles tests renderRecipeYAML against the actual
// recipe files from the goose_agent image, simulating the production path.
func TestRenderRecipe_RealRecipeFiles(t *testing.T) {
	recipesDir := "projects/agent_platform/goose_agent/image/recipes"

	entries, err := os.ReadDir(recipesDir)
	if err != nil {
		t.Skipf("recipe files not available (run via bazel test): %v", err)
	}

	if len(entries) == 0 {
		t.Fatal("no recipe files found")
	}

	// A realistic multi-line task with YAML-special characters.
	task := "Review files changed in commits 01KKJ150C7Y10SQG0E7Z88K84G..8a950f25 on main.\n" +
		"For each Go or Python source file that was modified and lacks a corresponding _test file, write tests.\n" +
		"Before starting:\n" +
		"- Check `gh pr list --search \"test\"` for existing test coverage PRs\n" +
		"- Check `gh issue list --search \"test\"` for related issues\n" +
		"- Skip files in generated code (zz_generated.*, *_types.go deepcopy)\n" +
		"Create one PR per project. Use conventional commit format: test(<project>): add coverage for <description>"

	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
			continue
		}

		name := strings.TrimSuffix(entry.Name(), ".yaml")
		t.Run(name, func(t *testing.T) {
			raw, err := os.ReadFile(filepath.Join(recipesDir, entry.Name()))
			if err != nil {
				t.Fatalf("failed to read recipe: %v", err)
			}

			// Parse YAML → map (same structure loadAgentsConfig uses).
			var recipe map[string]any
			if err := yaml.Unmarshal(raw, &recipe); err != nil {
				t.Fatalf("failed to parse recipe YAML: %v", err)
			}

			// Simulate JSON roundtrip (Helm toJson → Go json.Unmarshal).
			jsonBytes, err := json.Marshal(recipe)
			if err != nil {
				t.Fatalf("json.Marshal recipe: %v", err)
			}
			var roundtripped map[string]any
			if err := json.Unmarshal(jsonBytes, &roundtripped); err != nil {
				t.Fatalf("json.Unmarshal recipe: %v", err)
			}

			rendered, err := renderRecipeYAML(roundtripped, task)
			if err != nil {
				t.Fatalf("renderRecipeYAML failed: %v", err)
			}

			var parsed map[string]any
			if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
				t.Fatalf("rendered YAML is not valid:\n%s\nparse error: %v", rendered, err)
			}

			if _, ok := parsed["title"]; !ok {
				t.Error("rendered recipe missing 'title' field")
			}
			if _, ok := parsed["prompt"]; !ok {
				t.Error("rendered recipe missing 'prompt' field")
			}

			prompt, _ := parsed["prompt"].(string)
			if strings.Contains(prompt, "{{ task_description") {
				t.Error("template variable was not substituted in prompt")
			}
			if !strings.Contains(prompt, "Review files changed") {
				t.Error("rendered prompt doesn't contain the task text")
			}
		})
	}
}

// TestRenderRecipe_ValuesYAMLRecipes validates recipes as they appear in the
// orchestrator Helm values (the authoritative source for production recipes).
// This catches recipes that exist in values.yaml but not as standalone files.
func TestRenderRecipe_ValuesYAMLRecipes(t *testing.T) {
	agentsJSON := `{
		"agents": [
			{
				"id": "code-fix",
				"recipe": {
					"version": "1.0.0",
					"title": "Code Fix",
					"description": "Fix code issues",
					"instructions": "Fix the described issue.\nRun bazel test //... to verify.\nCommit using conventional commits format and create a PR.",
					"prompt": "{{ task_description | indent(2) }}",
					"parameters": [{"key": "task_description", "description": "The task", "input_type": "string", "requirement": "required"}]
				}
			},
			{
				"id": "feature",
				"recipe": {
					"version": "1.0.0",
					"title": "Feature",
					"description": "Implement a new feature with tests",
					"instructions": "Implement the described feature.\nFollow existing patterns.\nWrite tests.\nRun bazel test //...",
					"prompt": "{{ task_description | indent(2) }}",
					"parameters": [{"key": "task_description", "description": "The feature", "input_type": "string", "requirement": "required"}]
				}
			},
			{
				"id": "pr-review",
				"recipe": {
					"version": "1.0.0",
					"title": "PR Review",
					"description": "Review a pull request",
					"instructions": "Review the specified pull request.\nEvaluate for correctness, style, security, tests.",
					"prompt": "{{ task_description | indent(2) }}",
					"parameters": [{"key": "task_description", "description": "PR to review", "input_type": "string", "requirement": "required"}]
				}
			}
		]
	}`

	var cfg struct {
		Agents []struct {
			ID     string         `json:"id"`
			Recipe map[string]any `json:"recipe"`
		} `json:"agents"`
	}
	if err := json.Unmarshal([]byte(agentsJSON), &cfg); err != nil {
		t.Fatalf("failed to parse test agents JSON: %v", err)
	}

	task := "Fix the \"authentication\" bug in login handler.\n" +
		"Check:\n" +
		"- Token expiry: value should be 3600s\n" +
		"- Session store: must use Redis (not in-memory)\n" +
		"Create PR with format: fix(auth): correct token expiry"

	for _, agent := range cfg.Agents {
		t.Run(agent.ID, func(t *testing.T) {
			rendered, err := renderRecipeYAML(agent.Recipe, task)
			if err != nil {
				t.Fatalf("renderRecipeYAML failed for %s: %v", agent.ID, err)
			}

			var parsed map[string]any
			if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
				t.Fatalf("rendered YAML for %s is not valid:\n%s\nparse error: %v", agent.ID, rendered, err)
			}
		})
	}
}

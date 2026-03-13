package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRenderRecipe_MarshalOnly(t *testing.T) {
	recipe := map[string]any{
		"prompt": "{{ task_description | indent(2) }}",
	}
	rendered, err := renderRecipeYAML(recipe)
	if err != nil {
		t.Fatal(err)
	}
	// Template variable must be preserved — goose handles substitution.
	if !strings.Contains(rendered, "task_description") {
		t.Fatalf("expected template variable to be preserved, got:\n%s", rendered)
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

	rendered, err := renderRecipeYAML(recipe)
	if err != nil {
		t.Fatal(err)
	}

	var parsed map[string]any
	if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
		t.Fatalf("rendered YAML is not valid:\n%s\nparse error: %v", rendered, err)
	}

	// Verify template variable is preserved for goose.
	prompt, _ := parsed["prompt"].(string)
	if !strings.Contains(prompt, "{{ task_description") {
		t.Fatalf("template variable should be preserved for goose, got:\n%s", prompt)
	}
}

// TestRenderRecipe_JSONRoundtrip simulates the Helm values → ConfigMap JSON →
// Go map[string]any → renderRecipeYAML path that recipes take in production.
func TestRenderRecipe_JSONRoundtrip(t *testing.T) {
	original := map[string]any{
		"version":     "1.0.0",
		"title":       "Code Fix",
		"description": "Fix code issues",
		"instructions": "Fix the described issue.\n" +
			"Run bazel test //... to verify.\n" +
			"Commit using conventional commits.\n\n" +
			"## Output Format\n" +
			"```goose-result\ntype: pr | issue\nurl: <URL>\nsummary: <summary>\n```\n",
		"prompt": "{{ task_description | indent(2) }}",
		"parameters": []any{
			map[string]any{
				"key":         "task_description",
				"description": "The task to perform",
				"input_type":  "string",
				"requirement": "required",
			},
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

	rendered, err := renderRecipeYAML(roundtripped)
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
	// Template variable must survive the roundtrip.
	prompt, _ := parsed["prompt"].(string)
	if !strings.Contains(prompt, "task_description") {
		t.Errorf("template variable lost after JSON roundtrip, prompt: %s", prompt)
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

			rendered, err := renderRecipeYAML(roundtripped)
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

			// Template variables must be preserved.
			prompt, _ := parsed["prompt"].(string)
			if !strings.Contains(prompt, "task_description") {
				t.Error("template variable was not preserved in prompt")
			}
		})
	}
}

// TestRenderRecipe_ValuesYAMLRecipes validates recipes as they appear in the
// orchestrator Helm values (the authoritative source for production recipes).
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

	for _, agent := range cfg.Agents {
		t.Run(agent.ID, func(t *testing.T) {
			rendered, err := renderRecipeYAML(agent.Recipe)
			if err != nil {
				t.Fatalf("renderRecipeYAML failed for %s: %v", agent.ID, err)
			}

			var parsed map[string]any
			if err := yaml.Unmarshal([]byte(rendered), &parsed); err != nil {
				t.Fatalf("rendered YAML for %s is not valid:\n%s\nparse error: %v", agent.ID, rendered, err)
			}

			// Template variables must be preserved.
			prompt, _ := parsed["prompt"].(string)
			if !strings.Contains(prompt, "task_description") {
				t.Errorf("template variable lost for %s, prompt: %s", agent.ID, prompt)
			}
		})
	}
}

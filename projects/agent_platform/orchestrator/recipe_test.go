package main

import (
	"strings"
	"testing"
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
	if !strings.Contains(rendered, "  line1\n  line2") {
		t.Fatalf("expected indented lines, got:\n%s", rendered)
	}
}

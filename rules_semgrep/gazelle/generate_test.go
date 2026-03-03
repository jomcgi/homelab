package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
)

func TestGenerateRules_PythonFilesPresent(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py", "utils.py", "README.md"},
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule, got %d", len(result.Gen))
	}

	r := result.Gen[0]
	if r.Kind() != "semgrep_test" {
		t.Errorf("rule kind = %q, want %q", r.Kind(), "semgrep_test")
	}
	if r.Name() != "semgrep_test" {
		t.Errorf("rule name = %q, want %q", r.Name(), "semgrep_test")
	}

	// Check srcs attribute exists (glob value)
	srcs := r.Attr("srcs")
	if srcs == nil {
		t.Error("srcs attribute is nil")
	}

	// Check rules attribute exists
	rules := r.Attr("rules")
	if rules == nil {
		t.Error("rules attribute is nil")
	}

	// Check imports matches gen count
	if len(result.Imports) != len(result.Gen) {
		t.Errorf("imports count %d != gen count %d", len(result.Imports), len(result.Gen))
	}
}

func TestGenerateRules_NoPythonFiles(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.go", "README.md", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules for non-Python package, got %d", len(result.Gen))
	}
}

func TestGenerateRules_EmptyDirectory(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "empty",
		RegularFiles: []string{},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules for empty directory, got %d", len(result.Gen))
	}
}

func TestGenerateRules_Disabled(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled: false,
			},
		},
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules when disabled, got %d", len(result.Gen))
	}
}

func TestGenerateRules_WithExcludeRules(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"no-exec", "no-eval"},
			},
		},
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule, got %d", len(result.Gen))
	}

	r := result.Gen[0]

	// Check exclude_rules attribute exists
	excludeRules := r.Attr("exclude_rules")
	if excludeRules == nil {
		t.Error("exclude_rules attribute is nil when excludeRules configured")
	}
}

func TestGenerateRules_MixedFiles(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.go", "helper.py", "README.md", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule for mixed files with .py, got %d", len(result.Gen))
	}

	if result.Gen[0].Kind() != "semgrep_test" {
		t.Errorf("rule kind = %q, want %q", result.Gen[0].Kind(), "semgrep_test")
	}
}

func TestHasPythonFiles(t *testing.T) {
	tests := []struct {
		name  string
		files []string
		want  bool
	}{
		{
			name:  "single Python file",
			files: []string{"main.py"},
			want:  true,
		},
		{
			name:  "multiple Python files",
			files: []string{"main.py", "utils.py", "test_app.py"},
			want:  true,
		},
		{
			name:  "no Python files",
			files: []string{"main.go", "README.md", "BUILD"},
			want:  false,
		},
		{
			name:  "empty list",
			files: []string{},
			want:  false,
		},
		{
			name:  "mixed files with Python",
			files: []string{"main.go", "helper.py", "README.md"},
			want:  true,
		},
		{
			name:  "py in filename but not extension",
			files: []string{"deploy.yaml", "pytest.ini"},
			want:  false,
		},
		{
			name:  "file ending with .py",
			files: []string{"conftest.py"},
			want:  true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := hasPythonFiles(tc.files)
			if got != tc.want {
				t.Errorf("hasPythonFiles(%v) = %v, want %v", tc.files, got, tc.want)
			}
		})
	}
}

func TestSortedExcludeRules(t *testing.T) {
	tests := []struct {
		name  string
		input []string
		want  []string
	}{
		{
			name:  "already sorted",
			input: []string{"a", "b", "c"},
			want:  []string{"a", "b", "c"},
		},
		{
			name:  "unsorted",
			input: []string{"no-eval", "no-assert", "no-exec"},
			want:  []string{"no-assert", "no-eval", "no-exec"},
		},
		{
			name:  "single item",
			input: []string{"rule1"},
			want:  []string{"rule1"},
		},
		{
			name:  "empty",
			input: []string{},
			want:  []string{},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := sortedExcludeRules(tc.input)

			if len(got) != len(tc.want) {
				t.Fatalf("sortedExcludeRules() returned %d items, want %d", len(got), len(tc.want))
			}

			for i, v := range got {
				if v != tc.want[i] {
					t.Errorf("sortedExcludeRules()[%d] = %q, want %q", i, v, tc.want[i])
				}
			}
		})
	}
}

func TestSortedExcludeRules_DoesNotMutateInput(t *testing.T) {
	input := []string{"c", "a", "b"}
	original := append([]string{}, input...)

	_ = sortedExcludeRules(input)

	for i, v := range input {
		if v != original[i] {
			t.Errorf("input was mutated: input[%d] = %q, original = %q", i, v, original[i])
		}
	}
}

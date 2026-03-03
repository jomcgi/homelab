package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestGenerateRules_PerFile(t *testing.T) {
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

	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	// Sorted: main.py, utils.py
	assertRule(t, result.Gen[0], "main_semgrep_test", []string{"main.py"})
	assertRule(t, result.Gen[1], "utils_semgrep_test", []string{"utils.py"})

	if len(result.Imports) != len(result.Gen) {
		t.Errorf("imports count %d != gen count %d", len(result.Imports), len(result.Gen))
	}
}

func TestGenerateRules_SingleFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
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

	assertRule(t, result.Gen[0], "main_semgrep_test", []string{"main.py"})
}

func TestGenerateRules_InitPy(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"__init__.py", "main.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	assertRule(t, result.Gen[0], "__init___semgrep_test", []string{"__init__.py"})
	assertRule(t, result.Gen[1], "main_semgrep_test", []string{"main.py"})
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
		t.Errorf("expected 0 rules for non-Python package, got %d", len(result.Gen))
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
		t.Errorf("expected 0 rules for empty directory, got %d", len(result.Gen))
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
		t.Errorf("expected 0 rules when disabled, got %d", len(result.Gen))
	}
}

func TestGenerateRules_WithExcludeRules(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"no-requests", "no-eval-exec"},
			},
		},
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py", "utils.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	for _, r := range result.Gen {
		if r.Attr("exclude_rules") == nil {
			t.Errorf("rule %q missing exclude_rules", r.Name())
		}
	}
}

func TestGenerateRules_TestFilesIncluded(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py", "main_test.py", "conftest.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 3 {
		t.Fatalf("expected 3 rules (including test files), got %d", len(result.Gen))
	}

	assertRule(t, result.Gen[0], "conftest_semgrep_test", []string{"conftest.py"})
	assertRule(t, result.Gen[1], "main_semgrep_test", []string{"main.py"})
	assertRule(t, result.Gen[2], "main_test_semgrep_test", []string{"main_test.py"})
}

func TestPythonFiles(t *testing.T) {
	tests := []struct {
		name  string
		files []string
		want  []string
	}{
		{
			name:  "mixed files",
			files: []string{"main.go", "utils.py", "main.py", "BUILD"},
			want:  []string{"main.py", "utils.py"},
		},
		{
			name:  "no python files",
			files: []string{"main.go", "README.md"},
			want:  nil,
		},
		{
			name:  "empty",
			files: []string{},
			want:  nil,
		},
		{
			name:  "py in filename but not extension",
			files: []string{"pytest.ini", "deploy.yaml"},
			want:  nil,
		},
		{
			name:  "sorted output",
			files: []string{"z.py", "a.py", "m.py"},
			want:  []string{"a.py", "m.py", "z.py"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := pythonFiles(tc.files)
			if len(got) != len(tc.want) {
				t.Fatalf("pythonFiles() = %v, want %v", got, tc.want)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("[%d] = %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

func TestSortedExcludeRules(t *testing.T) {
	got := sortedExcludeRules([]string{"no-eval", "no-assert", "no-exec"})
	want := []string{"no-assert", "no-eval", "no-exec"}

	if len(got) != len(want) {
		t.Fatalf("got %d items, want %d", len(got), len(want))
	}
	for i, v := range got {
		if v != want[i] {
			t.Errorf("[%d] = %q, want %q", i, v, want[i])
		}
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

// assertRule checks a rule's name, kind, and srcs.
func assertRule(t *testing.T, r *rule.Rule, wantName string, wantSrcs []string) {
	t.Helper()
	if r.Kind() != "semgrep_test" {
		t.Errorf("rule kind = %q, want %q", r.Kind(), "semgrep_test")
	}
	if r.Name() != wantName {
		t.Errorf("rule name = %q, want %q", r.Name(), wantName)
	}
	srcs := r.AttrStrings("srcs")
	if len(srcs) != len(wantSrcs) {
		t.Errorf("rule %q srcs = %v, want %v", r.Name(), srcs, wantSrcs)
		return
	}
	for i := range srcs {
		if srcs[i] != wantSrcs[i] {
			t.Errorf("rule %q srcs[%d] = %q, want %q", r.Name(), i, srcs[i], wantSrcs[i])
		}
	}
}

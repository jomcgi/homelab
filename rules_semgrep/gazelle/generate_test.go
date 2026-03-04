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

// --- Helper functions for building test BUILD files ---

// buildFileWithRules creates a BUILD file with the given rules inserted.
func buildFileWithRules(rules ...*rule.Rule) *rule.File {
	f, _ := rule.LoadData("BUILD", "", nil)
	for _, r := range rules {
		r.Insert(f)
	}
	return f
}

// newPyBinary creates a py_venv_binary rule with the given name and main attribute.
func newPyBinary(name, main string) *rule.Rule {
	r := rule.NewRule("py_venv_binary", name)
	r.SetAttr("main", main)
	return r
}

// newPyLibrary creates a py_library rule with the given name and srcs.
func newPyLibrary(name string, srcs []string) *rule.Rule {
	r := rule.NewRule("py_library", name)
	r.SetAttr("srcs", srcs)
	return r
}

// newPyLibraryWithDeps creates a py_library rule with srcs and deps.
func newPyLibraryWithDeps(name string, srcs []string, deps []string) *rule.Rule {
	r := rule.NewRule("py_library", name)
	r.SetAttr("srcs", srcs)
	r.SetAttr("deps", deps)
	return r
}

// newPyBinaryWithDeps creates a py_venv_binary rule with main and deps.
func newPyBinaryWithDeps(name, main string, deps []string) *rule.Rule {
	r := rule.NewRule("py_venv_binary", name)
	r.SetAttr("main", main)
	r.SetAttr("deps", deps)
	return r
}

// --- Tests for binary-based semgrep test generation ---

func TestGenerateRules_WithBinary(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	binaryRule := newPyBinary("main", "main.py")
	buildFile := buildFileWithRules(binaryRule)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"__init__.py", "main.py", "utils.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for binary + 2 per-file semgrep_test for orphans
	if len(result.Gen) != 3 {
		t.Fatalf("expected 3 generated rules, got %d", len(result.Gen))
	}

	// First rule: semgrep_target_test for the binary
	targetRule := result.Gen[0]
	if targetRule.Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want %q", targetRule.Kind(), "semgrep_target_test")
	}
	if targetRule.Name() != "main_semgrep_test" {
		t.Errorf("rule[0] name = %q, want %q", targetRule.Name(), "main_semgrep_test")
	}
	if targetRule.AttrString("target") != ":main" {
		t.Errorf("rule[0] target = %q, want %q", targetRule.AttrString("target"), ":main")
	}
	targetRules := targetRule.AttrStrings("rules")
	if len(targetRules) != 1 || targetRules[0] != "//semgrep_rules:python_rules" {
		t.Errorf("rule[0] rules = %v, want [//semgrep_rules:python_rules]", targetRules)
	}

	// Remaining rules: per-file semgrep_test for orphans (sorted: __init__.py, utils.py)
	assertRule(t, result.Gen[1], "__init___semgrep_test", []string{"__init__.py"})
	assertRule(t, result.Gen[2], "utils_semgrep_test", []string{"utils.py"})

	if len(result.Imports) != len(result.Gen) {
		t.Errorf("imports count %d != gen count %d", len(result.Imports), len(result.Gen))
	}
}

func TestGenerateRules_MultipleBinaries(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	scraperBin := newPyBinary("scraper", "scraper_main.py")
	embedderBin := newPyBinary("embedder", "embedder_main.py")
	buildFile := buildFileWithRules(scraperBin, embedderBin)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/pipeline",
		RegularFiles: []string{"__init__.py", "config.py", "embedder_main.py", "models.py", "scraper_main.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 2 semgrep_target_test + 3 per-file orphan semgrep_test
	if len(result.Gen) != 5 {
		t.Fatalf("expected 5 generated rules, got %d", len(result.Gen))
	}

	// Binary rules (sorted by binary name: embedder, scraper)
	if result.Gen[0].Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", result.Gen[0].Kind())
	}
	if result.Gen[0].AttrString("target") != ":embedder" {
		t.Errorf("rule[0] target = %q, want :embedder", result.Gen[0].AttrString("target"))
	}

	if result.Gen[1].Kind() != "semgrep_target_test" {
		t.Errorf("rule[1] kind = %q, want semgrep_target_test", result.Gen[1].Kind())
	}
	if result.Gen[1].AttrString("target") != ":scraper" {
		t.Errorf("rule[1] target = %q, want :scraper", result.Gen[1].AttrString("target"))
	}

	// Orphan per-file rules (sorted: __init__.py, config.py, models.py)
	assertRule(t, result.Gen[2], "__init___semgrep_test", []string{"__init__.py"})
	assertRule(t, result.Gen[3], "config_semgrep_test", []string{"config.py"})
	assertRule(t, result.Gen[4], "models_semgrep_test", []string{"models.py"})
}

func TestGenerateRules_NoBinaries_FallsBackToPerFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	lib := newPyLibrary("mylib", []string{"lib.py", "helpers.py"})
	buildFile := buildFileWithRules(lib)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"helpers.py", "lib.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// No binaries, so all files get per-file semgrep_test
	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	assertRule(t, result.Gen[0], "helpers_semgrep_test", []string{"helpers.py"})
	assertRule(t, result.Gen[1], "lib_semgrep_test", []string{"lib.py"})
}

func TestGenerateRules_BinaryWithExcludeRules(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"no-requests", "no-eval-exec"},
			},
		},
	}

	binaryRule := newPyBinary("server", "server.py")
	buildFile := buildFileWithRules(binaryRule)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"server.py", "utils.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	// The semgrep_target_test for the binary should have exclude_rules
	targetRule := result.Gen[0]
	if targetRule.Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", targetRule.Kind())
	}
	if targetRule.Attr("exclude_rules") == nil {
		t.Error("semgrep_target_test rule missing exclude_rules attribute")
	}

	// The orphan per-file rule should also have exclude_rules
	orphanRule := result.Gen[1]
	if orphanRule.Kind() != "semgrep_test" {
		t.Errorf("rule[1] kind = %q, want semgrep_test", orphanRule.Kind())
	}
	if orphanRule.Attr("exclude_rules") == nil {
		t.Error("orphan semgrep_test rule missing exclude_rules attribute")
	}
}

func TestGenerateRules_StaleTargetTestsRemoved(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	// BUILD file has an old semgrep_target_test that no longer corresponds to a binary
	oldTargetTest := rule.NewRule("semgrep_target_test", "old_binary_semgrep_test")
	oldTargetTest.SetAttr("target", ":old_binary")
	buildFile := buildFileWithRules(oldTargetTest)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Should generate per-file rules (no binaries in BUILD)
	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule, got %d", len(result.Gen))
	}

	// The stale semgrep_target_test should appear in Empty
	foundStale := false
	for _, r := range result.Empty {
		if r.Kind() == "semgrep_target_test" && r.Name() == "old_binary_semgrep_test" {
			foundStale = true
			break
		}
	}
	if !foundStale {
		t.Error("stale semgrep_target_test 'old_binary_semgrep_test' should appear in result.Empty")
	}
}

func TestGenerateRules_PyBinaryKindAlsoDetected(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	// Use py_binary instead of py_venv_binary
	pyBin := rule.NewRule("py_binary", "cli")
	pyBin.SetAttr("main", "cli.py")
	buildFile := buildFileWithRules(pyBin)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/cli",
		RegularFiles: []string{"cli.py", "helpers.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for py_binary + 1 per-file semgrep_test for orphan
	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 generated rules, got %d", len(result.Gen))
	}

	// First rule: semgrep_target_test for the py_binary
	targetRule := result.Gen[0]
	if targetRule.Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", targetRule.Kind())
	}
	if targetRule.Name() != "cli_semgrep_test" {
		t.Errorf("rule[0] name = %q, want cli_semgrep_test", targetRule.Name())
	}
	if targetRule.AttrString("target") != ":cli" {
		t.Errorf("rule[0] target = %q, want :cli", targetRule.AttrString("target"))
	}

	// Second rule: per-file semgrep_test for orphan
	assertRule(t, result.Gen[1], "helpers_semgrep_test", []string{"helpers.py"})
}

func TestGenerateRules_BinaryWithLocalLibDeps(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	// Simulate a package like knowledge_graph/app:
	// - scraper binary depends on :config and :models (local libraries)
	// - config.py and models.py are srcs of those libraries
	// - __init__.py is NOT a dep of any binary
	configLib := newPyLibrary("config", []string{"config.py"})
	modelsLib := newPyLibrary("models", []string{"models.py"})
	scraperMain := newPyLibraryWithDeps("scraper_main", []string{"scraper_main.py"}, []string{":config", ":models"})
	scraperBin := newPyBinaryWithDeps("scraper", "scraper_main.py", []string{":scraper_main"})
	buildFile := buildFileWithRules(configLib, modelsLib, scraperMain, scraperBin)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/pipeline",
		RegularFiles: []string{"__init__.py", "config.py", "models.py", "scraper_main.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for binary + 1 per-file semgrep_test for __init__.py only
	// config.py and models.py are covered by the binary's transitive local deps
	if len(result.Gen) != 2 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Kind()+"/"+r.Name())
		}
		t.Fatalf("expected 2 generated rules, got %d: %v", len(result.Gen), names)
	}

	// First rule: semgrep_target_test for the binary
	if result.Gen[0].Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", result.Gen[0].Kind())
	}
	if result.Gen[0].AttrString("target") != ":scraper" {
		t.Errorf("rule[0] target = %q, want :scraper", result.Gen[0].AttrString("target"))
	}

	// Second rule: only __init__.py as orphan
	assertRule(t, result.Gen[1], "__init___semgrep_test", []string{"__init__.py"})
}

func TestGenerateRules_MultipleBinariesWithSharedDeps(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	// Two binaries that share some deps. Like knowledge_graph/app.
	configLib := newPyLibrary("config", []string{"config.py"})
	modelsLib := newPyLibrary("models", []string{"models.py"})
	storageLib := newPyLibraryWithDeps("storage", []string{"storage.py"}, []string{":models"})
	telemetryLib := newPyLibrary("telemetry", []string{"telemetry.py"})
	chunkerLib := newPyLibraryWithDeps("chunker", []string{"chunker.py"}, []string{":models"})

	scraperMainLib := newPyLibraryWithDeps("scraper_main", []string{"scraper_main.py"},
		[]string{":config", ":models", ":storage", ":telemetry"})
	scraperBin := newPyBinaryWithDeps("scraper", "scraper_main.py", []string{":scraper_main"})

	embedderMainLib := newPyLibraryWithDeps("embedder_main", []string{"embedder_main.py"},
		[]string{":chunker", ":config", ":storage", ":telemetry"})
	embedderBin := newPyBinaryWithDeps("embedder", "embedder_main.py", []string{":embedder_main"})

	buildFile := buildFileWithRules(
		configLib, modelsLib, storageLib, telemetryLib, chunkerLib,
		scraperMainLib, scraperBin, embedderMainLib, embedderBin,
	)

	args := language.GenerateArgs{
		Config: c,
		Dir:    "/tmp/test",
		Rel:    "services/pipeline",
		RegularFiles: []string{
			"__init__.py", "chunker.py", "config.py", "embedder_main.py",
			"models.py", "scraper_main.py", "storage.py", "telemetry.py",
		},
		File: buildFile,
	}

	result := generateRules(args)

	// Expect: 2 semgrep_target_test (embedder, scraper) + 1 orphan (__init__.py)
	// All other files are transitively reachable from the binaries
	if len(result.Gen) != 3 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Kind()+"/"+r.Name())
		}
		t.Fatalf("expected 3 generated rules, got %d: %v", len(result.Gen), names)
	}

	if result.Gen[0].Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", result.Gen[0].Kind())
	}
	if result.Gen[0].AttrString("target") != ":embedder" {
		t.Errorf("rule[0] target = %q, want :embedder", result.Gen[0].AttrString("target"))
	}

	if result.Gen[1].Kind() != "semgrep_target_test" {
		t.Errorf("rule[1] kind = %q, want semgrep_target_test", result.Gen[1].Kind())
	}
	if result.Gen[1].AttrString("target") != ":scraper" {
		t.Errorf("rule[1] target = %q, want :scraper", result.Gen[1].AttrString("target"))
	}

	// Only __init__.py is orphaned
	assertRule(t, result.Gen[2], "__init___semgrep_test", []string{"__init__.py"})
}

func TestGenerateRules_StalePerFileTestsRemovedWhenBinaryCovers(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	// Simulate: existing BUILD has per-file semgrep_tests AND a binary with deps
	configLib := newPyLibrary("config", []string{"config.py"})
	modelsLib := newPyLibrary("models", []string{"models.py"})
	scraperMainLib := newPyLibraryWithDeps("scraper_main", []string{"scraper_main.py"}, []string{":config", ":models"})
	scraperBin := newPyBinaryWithDeps("scraper", "scraper_main.py", []string{":scraper_main"})

	// Old per-file semgrep tests
	oldInitTest := rule.NewRule("semgrep_test", "__init___semgrep_test")
	oldInitTest.SetAttr("srcs", []string{"__init__.py"})
	oldConfigTest := rule.NewRule("semgrep_test", "config_semgrep_test")
	oldConfigTest.SetAttr("srcs", []string{"config.py"})
	oldModelsTest := rule.NewRule("semgrep_test", "models_semgrep_test")
	oldModelsTest.SetAttr("srcs", []string{"models.py"})
	oldScraperTest := rule.NewRule("semgrep_test", "scraper_main_semgrep_test")
	oldScraperTest.SetAttr("srcs", []string{"scraper_main.py"})

	buildFile := buildFileWithRules(
		configLib, modelsLib, scraperMainLib, scraperBin,
		oldInitTest, oldConfigTest, oldModelsTest, oldScraperTest,
	)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/pipeline",
		RegularFiles: []string{"__init__.py", "config.py", "models.py", "scraper_main.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test + 1 orphan (init)
	if len(result.Gen) != 2 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Kind()+"/"+r.Name())
		}
		t.Fatalf("expected 2 generated rules, got %d: %v", len(result.Gen), names)
	}

	// Verify stale rules
	// config_semgrep_test, models_semgrep_test, scraper_main_semgrep_test should be stale
	staleNames := make(map[string]bool)
	for _, r := range result.Empty {
		staleNames[r.Kind()+"/"+r.Name()] = true
		t.Logf("stale: %s/%s", r.Kind(), r.Name())
	}

	expectedStale := []string{
		"semgrep_test/config_semgrep_test",
		"semgrep_test/models_semgrep_test",
		"semgrep_test/scraper_main_semgrep_test",
	}
	for _, s := range expectedStale {
		if !staleNames[s] {
			t.Errorf("expected %q in Empty set but not found", s)
		}
	}

	// __init___semgrep_test should NOT be stale (it's an orphan)
	if staleNames["semgrep_test/__init___semgrep_test"] {
		t.Error("__init___semgrep_test should NOT be in Empty set")
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

# Semgrep Configurability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the rules_semgrep Gazelle extension configurable via directives for target kinds and languages, enabling py3_image scanning and future multi-language support.

**Architecture:** Two new Gazelle directives (`semgrep_target_kinds`, `semgrep_languages`) replace hardcoded binary kind maps and rule config strings. For macro targets like `py3_image`, Gazelle reads a configurable attribute (e.g., `binary`) to find the real target for the aspect. The aspect drops its `.py` extension filter to collect all source files.

**Tech Stack:** Starlark (aspect.bzl), Go (Gazelle extension), Bazel

---

### Task 1: Remove `.py` extension filter from aspect

**Files:**

- Modify: `rules_semgrep/aspect.bzl`

**Context:** The aspect currently hardcodes `f.extension == "py"` to filter files. We need it to collect ALL non-external source files so that semgrep can scan any language. Semgrep rules determine what to scan — a `.go` file passed with Python rules is simply skipped.

**Step 1: Update the aspect to remove extension filtering**

In `rules_semgrep/aspect.bzl`, make these changes:

Line 1 — update doc string:

```starlark
"""Bazel aspect for collecting transitive source files for semgrep scanning."""
```

Lines 3-6 — update provider doc:

```starlark
SemgrepSourcesInfo = provider(
    doc = "Carries transitive source files for semgrep scanning.",
    fields = {"sources": "depset of source files from the main repository"},
)
```

Line 11 — update comment:

```starlark
    # Collect source files from srcs attribute
```

Line 15 — remove `.py` filter, keep external filter:

```starlark
                if not f.short_path.startswith("../"):
```

Line 18 — update comment:

```starlark
    # Collect from main attribute (py_venv_binary)
```

Line 25 — same removal:

```starlark
                    if not f.short_path.startswith("../"):
```

Line 36 — rename variable for clarity:

```starlark
        sources = depset(py_sources, transitive = transitive),
```

(Keep the variable name `py_sources` — renaming it is optional cosmetic change, skip for now.)

**Step 2: Run the existing integration test to verify the aspect still works**

Run: `bazel test //rules_semgrep/... --test_output=errors`

Expected: All existing tests pass. The aspect now collects all files but the semgrep rules still only match `.py` files.

**Step 3: Commit**

```bash
git add rules_semgrep/aspect.bzl
git commit -m "refactor(semgrep): remove .py extension filter from aspect

The aspect now collects all non-external source files. Semgrep rules
determine which languages to scan."
```

---

### Task 2: Add language mapping to Gazelle config

**Files:**

- Modify: `rules_semgrep/gazelle/config.go`

**Context:** The config struct needs two new fields: `targetKinds` (map of kind → target attr name) and `languages` (list of language keys). Each language maps to file extensions and semgrep rule configs. These are populated from directives and inherited through the directory tree.

**Step 1: Write failing tests for the new config fields and directive parsing**

Add to a new file or append to existing config test. Create `rules_semgrep/gazelle/config_test.go`:

```go
package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestConfigure_DefaultTargetKinds(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}
	configure(c, "", nil)
	cfg := getSemgrepConfig(c)

	if _, ok := cfg.targetKinds["py_venv_binary"]; !ok {
		t.Error("default targetKinds should include py_venv_binary")
	}
	if cfg.targetKinds["py_venv_binary"] != "" {
		t.Errorf("py_venv_binary target attr should be empty (self), got %q", cfg.targetKinds["py_venv_binary"])
	}
}

func TestConfigure_DefaultLanguages(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}
	configure(c, "", nil)
	cfg := getSemgrepConfig(c)

	if len(cfg.languages) != 1 || cfg.languages[0] != "py" {
		t.Errorf("default languages should be [py], got %v", cfg.languages)
	}
}

func TestConfigure_TargetKindsDirective(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}
	configure(c, "", nil) // set defaults

	f, _ := rule.LoadData("BUILD", "", []rule.Directive{
		{Key: "semgrep_target_kinds", Value: "py_venv_binary,py3_image"},
	})
	configure(c, "services", f)
	cfg := getSemgrepConfig(c)

	if len(cfg.targetKinds) != 2 {
		t.Fatalf("expected 2 target kinds, got %d: %v", len(cfg.targetKinds), cfg.targetKinds)
	}
	if _, ok := cfg.targetKinds["py_venv_binary"]; !ok {
		t.Error("targetKinds should include py_venv_binary")
	}
	if _, ok := cfg.targetKinds["py3_image"]; !ok {
		t.Error("targetKinds should include py3_image")
	}
}

func TestConfigure_TargetKindsWithAttr(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}
	configure(c, "", nil)

	f, _ := rule.LoadData("BUILD", "", []rule.Directive{
		{Key: "semgrep_target_kinds", Value: "py_venv_binary,py3_image=binary"},
	})
	configure(c, "services", f)
	cfg := getSemgrepConfig(c)

	if cfg.targetKinds["py3_image"] != "binary" {
		t.Errorf("py3_image target attr should be 'binary', got %q", cfg.targetKinds["py3_image"])
	}
	if cfg.targetKinds["py_venv_binary"] != "" {
		t.Errorf("py_venv_binary target attr should be empty, got %q", cfg.targetKinds["py_venv_binary"])
	}
}

func TestConfigure_LanguagesDirective(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}
	configure(c, "", nil)

	f, _ := rule.LoadData("BUILD", "", []rule.Directive{
		{Key: "semgrep_languages", Value: "py,go"},
	})
	configure(c, "services", f)
	cfg := getSemgrepConfig(c)

	if len(cfg.languages) != 2 {
		t.Fatalf("expected 2 languages, got %d", len(cfg.languages))
	}
	if cfg.languages[0] != "py" || cfg.languages[1] != "go" {
		t.Errorf("languages should be [py, go], got %v", cfg.languages)
	}
}

func TestConfigure_InheritanceFromParent(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	// Parent sets target kinds
	parentF, _ := rule.LoadData("BUILD", "", []rule.Directive{
		{Key: "semgrep_target_kinds", Value: "py_venv_binary,py3_image=binary"},
		{Key: "semgrep_languages", Value: "py,go"},
	})
	configure(c, "", parentF)

	// Child inherits without overriding
	configure(c, "services/myapp", nil)
	cfg := getSemgrepConfig(c)

	if len(cfg.targetKinds) != 2 {
		t.Errorf("child should inherit parent's targetKinds, got %v", cfg.targetKinds)
	}
	if len(cfg.languages) != 2 {
		t.Errorf("child should inherit parent's languages, got %v", cfg.languages)
	}
}
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=errors`

Expected: FAIL — `cfg.targetKinds` and `cfg.languages` don't exist yet.

**Step 3: Implement the config changes**

In `rules_semgrep/gazelle/config.go`:

Add `targetKinds` and `languages` fields to the struct (after line 15):

```go
type semgrepConfig struct {
	enabled      bool
	excludeRules []string
	targetKinds  map[string]string // kind -> target attr ("" = target itself)
	languages    []string          // language keys (e.g., "py", "go")
}
```

Add language mapping constants (after imports, before the struct):

```go
// langRules maps language keys to semgrep rule targets.
var langRules = map[string]string{
	"py": "//semgrep_rules:python_rules",
	"go": "//semgrep_rules:go_rules",
}

// langExtensions maps language keys to file extensions for orphan detection.
var langExtensions = map[string]string{
	"py": ".py",
	"go": ".go",
}
```

Update `getSemgrepConfig` default (lines 26-28) to include defaults:

```go
	return &semgrepConfig{
		enabled:     true,
		targetKinds: map[string]string{"py_venv_binary": ""},
		languages:   []string{"py"},
	}
```

Update `configure` clone logic (lines 37-40) to copy new fields:

```go
	cfg := &semgrepConfig{
		enabled:      parent.enabled,
		excludeRules: append([]string{}, parent.excludeRules...),
		targetKinds:  copyMap(parent.targetKinds),
		languages:    append([]string{}, parent.languages...),
	}
```

Add a `copyMap` helper:

```go
func copyMap(m map[string]string) map[string]string {
	out := make(map[string]string, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}
```

Add directive handlers in the switch (after line 57, before the closing `}`):

```go
			case "semgrep_target_kinds":
				// # gazelle:semgrep_target_kinds py_venv_binary,py3_image=binary
				// Each item is either "kind" (target = self) or "kind=attr" (follow attr).
				cfg.targetKinds = make(map[string]string)
				for _, item := range strings.Split(d.Value, ",") {
					item = strings.TrimSpace(item)
					if item == "" {
						continue
					}
					if parts := strings.SplitN(item, "=", 2); len(parts) == 2 {
						cfg.targetKinds[parts[0]] = parts[1]
					} else {
						cfg.targetKinds[item] = ""
					}
				}
			case "semgrep_languages":
				// # gazelle:semgrep_languages py,go
				cfg.languages = nil
				for _, lang := range strings.Split(d.Value, ",") {
					lang = strings.TrimSpace(lang)
					if lang != "" {
						cfg.languages = append(cfg.languages, lang)
					}
				}
```

**Step 4: Run tests**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=errors`

Expected: All tests pass including the new config tests.

**Step 5: Commit**

```bash
git add rules_semgrep/gazelle/config.go rules_semgrep/gazelle/config_test.go
git commit -m "feat(semgrep): add target_kinds and languages directives to gazelle config"
```

---

### Task 3: Update language.go to register new directives

**Files:**

- Modify: `rules_semgrep/gazelle/language.go`
- Modify: `rules_semgrep/gazelle/language_test.go`

**Context:** The new directives must be registered in `KnownDirectives()` so Gazelle passes them to our `Configure` method.

**Step 1: Update the failing test first**

In `rules_semgrep/gazelle/language_test.go`, update `TestSemgrepLang_KnownDirectives` (lines 33-56). Change the `expected` slice:

```go
	expected := []string{
		"semgrep",
		"semgrep_exclude_rules",
		"semgrep_target_kinds",
		"semgrep_languages",
	}
```

**Step 2: Run test to verify it fails**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_filter=TestSemgrepLang_KnownDirectives --test_output=errors`

Expected: FAIL — 4 expected, 2 returned.

**Step 3: Add the directives to language.go**

In `rules_semgrep/gazelle/language.go`, update `KnownDirectives()` (lines 42-46):

```go
func (l *semgrepLang) KnownDirectives() []string {
	return []string{
		"semgrep",
		"semgrep_exclude_rules",
		"semgrep_target_kinds",
		"semgrep_languages",
	}
}
```

**Step 4: Run tests**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=errors`

Expected: All pass.

**Step 5: Commit**

```bash
git add rules_semgrep/gazelle/language.go rules_semgrep/gazelle/language_test.go
git commit -m "feat(semgrep): register semgrep_target_kinds and semgrep_languages directives"
```

---

### Task 4: Write failing tests for config-driven generation

**Files:**

- Modify: `rules_semgrep/gazelle/generate_test.go`

**Context:** We need tests that verify: (1) target kinds from config are used instead of hardcoded map, (2) `py3_image` with `binary` attr indirection works, (3) language-driven rules config is emitted, (4) multi-language orphan detection uses configured extensions.

**Step 1: Add helper for creating py3_image rules**

Add after `newPyBinaryWithDeps` (~line 309):

```go
// newPy3Image creates a py3_image rule with the given name and binary attr.
func newPy3Image(name, binary string) *rule.Rule {
	r := rule.NewRule("py3_image", name)
	r.SetAttr("binary", binary)
	return r
}

// configWithTargetKinds creates a config with custom target kinds.
func configWithTargetKinds(kinds map[string]string) *config.Config {
	return &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:     true,
				targetKinds: kinds,
				languages:   []string{"py"},
			},
		},
	}
}

// configWithLanguages creates a config with custom languages.
func configWithLanguages(kinds map[string]string, langs []string) *config.Config {
	return &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:     true,
				targetKinds: kinds,
				languages:   langs,
			},
		},
	}
}
```

**Step 2: Add test for py3_image target kind with binary attr indirection**

```go
func TestGenerateRules_Py3ImageTargetKind(t *testing.T) {
	c := configWithTargetKinds(map[string]string{
		"py_venv_binary": "",
		"py3_image":      "binary",
	})

	// Package has a py3_image pointing to a cross-package binary
	image := newPy3Image("scraper-image", "//services/knowledge_graph/app:scraper")
	buildFile := buildFileWithRules(image)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/knowledge_graph",
		RegularFiles: []string{"__init__.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for the image (targeting the binary) + 1 orphan
	if len(result.Gen) != 2 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Kind()+"/"+r.Name())
		}
		t.Fatalf("expected 2 generated rules, got %d: %v", len(result.Gen), names)
	}

	// Target test should point to the binary, not the image
	targetRule := result.Gen[0]
	if targetRule.Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", targetRule.Kind())
	}
	if targetRule.AttrString("target") != "//services/knowledge_graph/app:scraper" {
		t.Errorf("rule[0] target = %q, want //services/knowledge_graph/app:scraper",
			targetRule.AttrString("target"))
	}
}

func TestGenerateRules_Py3ImageLocalBinary(t *testing.T) {
	c := configWithTargetKinds(map[string]string{
		"py_venv_binary": "",
		"py3_image":      "binary",
	})

	// Local binary + image in same package
	binary := newPyBinary("update", "update.py")
	image := newPy3Image("update_image", ":update")
	buildFile := buildFileWithRules(binary, image)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/hikes/update_forecast",
		RegularFiles: []string{"__init__.py", "update.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for binary + 1 for image (targeting binary) + 1 orphan
	// But the binary and image both target the same binary, so we should deduplicate.
	// Actually: both py_venv_binary and py3_image are target kinds. The binary generates
	// a semgrep_target_test(target = ":update"). The image generates another
	// semgrep_target_test(target = ":update"). We should deduplicate by target.
	//
	// Expect: 1 semgrep_target_test (deduplicated) + 1 orphan
	if len(result.Gen) != 2 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Kind()+"/"+r.Name()+" target="+r.AttrString("target"))
		}
		t.Fatalf("expected 2 generated rules, got %d: %v", len(result.Gen), names)
	}

	// First: target test for the binary
	if result.Gen[0].Kind() != "semgrep_target_test" {
		t.Errorf("rule[0] kind = %q, want semgrep_target_test", result.Gen[0].Kind())
	}

	// Second: orphan __init__.py
	assertRule(t, result.Gen[1], "__init___semgrep_test", []string{"__init__.py"})
}

func TestGenerateRules_LanguageRulesConfig(t *testing.T) {
	c := configWithLanguages(
		map[string]string{"py_venv_binary": ""},
		[]string{"py", "go"},
	)

	binary := newPyBinary("server", "server.py")
	buildFile := buildFileWithRules(binary)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"server.py", "helpers.go"},
		File:         buildFile,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test with both py and go rules + 1 orphan for helpers.go
	if len(result.Gen) < 1 {
		t.Fatalf("expected at least 1 generated rule, got %d", len(result.Gen))
	}

	targetRule := result.Gen[0]
	rules := targetRule.AttrStrings("rules")
	if len(rules) != 2 {
		t.Fatalf("target test should have 2 rule configs, got %d: %v", len(rules), rules)
	}
	// Rules should be sorted
	if rules[0] != "//semgrep_rules:go_rules" || rules[1] != "//semgrep_rules:python_rules" {
		t.Errorf("target test rules = %v, want [//semgrep_rules:go_rules, //semgrep_rules:python_rules]", rules)
	}
}

func TestGenerateRules_MultiLangOrphans(t *testing.T) {
	c := configWithLanguages(
		map[string]string{"py_venv_binary": ""},
		[]string{"py", "go"},
	)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py", "utils.go", "README.md"},
	}

	result := generateRules(args)

	// No binaries → per-file tests for both .py and .go files
	if len(result.Gen) != 2 {
		var names []string
		for _, r := range result.Gen {
			names = append(names, r.Name())
		}
		t.Fatalf("expected 2 generated rules, got %d: %v", len(result.Gen), names)
	}

	// Sorted: main.py before utils.go
	assertRule(t, result.Gen[0], "main_semgrep_test", []string{"main.py"})
	assertRule(t, result.Gen[1], "utils_semgrep_test", []string{"utils.go"})
}

func TestGenerateRules_TargetKindNotInConfig(t *testing.T) {
	// Only py_venv_binary configured — py3_image should be ignored
	c := configWithTargetKinds(map[string]string{
		"py_venv_binary": "",
	})

	image := newPy3Image("scraper-image", "//app:scraper")
	buildFile := buildFileWithRules(image)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"__init__.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	// No binaries of configured kinds — falls back to per-file
	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 per-file rule, got %d", len(result.Gen))
	}
	assertRule(t, result.Gen[0], "__init___semgrep_test", []string{"__init__.py"})
}
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=errors`

Expected: FAIL — new tests reference fields and logic that don't exist yet.

**Step 3: Commit the failing tests**

```bash
git add rules_semgrep/gazelle/generate_test.go
git commit -m "test(semgrep): add failing tests for configurable target kinds and languages"
```

---

### Task 5: Implement config-driven generation in generate.go

**Files:**

- Modify: `rules_semgrep/gazelle/generate.go`

**Context:** Replace hardcoded `binaryKinds` with `cfg.targetKinds`. Add attr indirection for kinds like `py3_image`. Replace hardcoded `"//semgrep_rules:python_rules"` with language-driven rule configs. Generalize `pythonFiles` to use configured extensions.

**Step 1: Replace hardcoded maps with config-driven logic**

Remove the `binaryKinds` global (lines 11-15). The `libraryKinds` map stays (it's used for dep walking).

Update `generateRules` to use `cfg.targetKinds`:

```go
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	if !cfg.enabled {
		return result
	}

	// Collect scannable files based on configured languages
	scanFiles := scannableFiles(args.RegularFiles, cfg.languages)
	if len(scanFiles) == 0 {
		result.Empty = staleRules(args, nil)
		return result
	}

	// Build the rules list from configured languages
	ruleConfigs := rulesForLanguages(cfg.languages)

	// Detect target-kind rules in the existing BUILD file
	targets := findTargets(args.File, cfg.targetKinds)

	if len(targets) > 0 {
		// Deduplicate by resolved target label
		seen := make(map[string]bool)

		// Build the set of .py files covered by binaries' transitive local deps.
		coveredFiles := coveredByBinaries(args.File, targets, cfg.targetKinds)

		for _, t := range targets {
			resolvedTarget := resolveTarget(t, cfg.targetKinds)
			if seen[resolvedTarget] {
				continue
			}
			seen[resolvedTarget] = true

			name := t.Name() + "_semgrep_test"
			r := rule.NewRule("semgrep_target_test", name)
			r.SetAttr("target", resolvedTarget)
			r.SetAttr("rules", ruleConfigs)
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}

		// Generate per-file semgrep_test for orphan files
		for _, f := range scanFiles {
			if coveredFiles[f] {
				continue
			}
			ext := fileExtension(f)
			name := strings.TrimSuffix(f, ext) + "_semgrep_test"
			r := rule.NewRule("semgrep_test", name)
			r.SetAttr("srcs", []string{f})
			r.SetAttr("rules", rulesForExtension(ext, cfg.languages))
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}
	} else {
		// No target-kind rules — fall back to per-file semgrep_test
		for _, f := range scanFiles {
			ext := fileExtension(f)
			name := strings.TrimSuffix(f, ext) + "_semgrep_test"
			r := rule.NewRule("semgrep_test", name)
			r.SetAttr("srcs", []string{f})
			r.SetAttr("rules", rulesForExtension(ext, cfg.languages))
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}
	}

	result.Empty = staleRules(args, result.Gen)
	return result
}
```

**Step 2: Add new helper functions**

Replace `findBinaries` with `findTargets`:

```go
// findTargets returns rules matching configured target kinds from the BUILD file.
func findTargets(f *rule.File, targetKinds map[string]string) []*rule.Rule {
	if f == nil {
		return nil
	}
	var targets []*rule.Rule
	for _, r := range f.Rules {
		if _, ok := targetKinds[r.Kind()]; ok {
			targets = append(targets, r)
		}
	}
	sort.Slice(targets, func(i, j int) bool {
		return targets[i].Name() < targets[j].Name()
	})
	return targets
}
```

Add `resolveTarget`:

```go
// resolveTarget returns the target label for a semgrep_target_test.
// For kinds with a target attr (e.g., py3_image.binary), reads that attr.
// For kinds without (e.g., py_venv_binary), returns ":name".
func resolveTarget(r *rule.Rule, targetKinds map[string]string) string {
	attr := targetKinds[r.Kind()]
	if attr != "" {
		// Read the configured attribute (e.g., "binary")
		val := r.AttrString(attr)
		if val != "" {
			return val
		}
	}
	return ":" + r.Name()
}
```

Replace `pythonFiles` with `scannableFiles`:

```go
// scannableFiles returns sorted files matching any configured language extension.
func scannableFiles(files []string, languages []string) []string {
	extSet := make(map[string]bool)
	for _, lang := range languages {
		if ext, ok := langExtensions[lang]; ok {
			extSet[ext] = true
		}
	}

	var matched []string
	for _, f := range files {
		if extSet[fileExtension(f)] {
			matched = append(matched, f)
		}
	}
	sort.Strings(matched)
	return matched
}

// fileExtension returns the file extension including the dot (e.g., ".py").
func fileExtension(f string) string {
	if i := strings.LastIndex(f, "."); i >= 0 {
		return f[i:]
	}
	return ""
}
```

Add rule config helpers:

```go
// rulesForLanguages returns sorted semgrep rule configs for all configured languages.
func rulesForLanguages(languages []string) []string {
	var rules []string
	for _, lang := range languages {
		if r, ok := langRules[lang]; ok {
			rules = append(rules, r)
		}
	}
	sort.Strings(rules)
	return rules
}

// rulesForExtension returns semgrep rule configs matching a file extension.
func rulesForExtension(ext string, languages []string) []string {
	var rules []string
	for _, lang := range languages {
		if langExtensions[lang] == ext {
			if r, ok := langRules[lang]; ok {
				rules = append(rules, r)
			}
		}
	}
	sort.Strings(rules)
	return rules
}
```

Update `coveredByBinaries` signature — it now receives `targetKinds` and only considers "self-target" kinds (not indirected kinds like py3_image) for local dep walking:

```go
func coveredByBinaries(f *rule.File, targets []*rule.Rule, targetKinds map[string]string) map[string]bool {
	if f == nil {
		return nil
	}

	ruleByName := make(map[string]*rule.Rule)
	for _, r := range f.Rules {
		ruleByName[r.Name()] = r
	}

	srcsByName := make(map[string][]string)
	for _, r := range f.Rules {
		kind := r.Kind()
		if targetKinds[kind] == "" || libraryKinds[kind] {
			// Only index self-targeting kinds and libraries for dep walking
			srcsByName[r.Name()] = r.AttrStrings("srcs")
		}
	}

	covered := make(map[string]bool)
	visited := make(map[string]bool)

	for _, t := range targets {
		// Only walk deps for self-targeting kinds (not indirected like py3_image)
		if targetKinds[t.Kind()] == "" {
			walkLocalDeps(t, ruleByName, srcsByName, covered, visited)
		}
	}

	return covered
}
```

**Step 3: Run tests**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=errors`

Expected: All tests pass including the new ones. Some existing tests may need minor adjustments if they relied on the old default config not having `targetKinds` — fix them by ensuring the default config is set up. The existing tests that use `&config.Config{Exts: make(map[string]interface{})}` should work because `getSemgrepConfig` returns defaults.

**Step 4: Commit**

```bash
git add rules_semgrep/gazelle/generate.go
git commit -m "feat(semgrep): implement config-driven target kinds and language rules in gazelle"
```

---

### Task 6: Add directive to root BUILD and regenerate

**Files:**

- Modify: `BUILD` (root)
- Run: `format` (includes gazelle)

**Context:** Add the `semgrep_target_kinds` directive to the root BUILD file to enable `py3_image` scanning across the repo.

**Step 1: Add the directive**

In the root `BUILD` file, after the existing `# gazelle:semgrep_exclude_rules` directives (around line 90-97), add:

```
# Semgrep: scan binary and image targets for cross-file analysis
# gazelle:semgrep_target_kinds py_venv_binary,py3_image=binary
```

**Step 2: Run format to regenerate BUILD files**

Run: `format`

Expected: Gazelle regenerates BUILD files. Services with `py3_image` targets (like `services/knowledge_graph/BUILD`) now get `semgrep_target_test` rules pointing to the underlying binaries.

Verify `services/knowledge_graph/BUILD` has new target tests:

```bash
grep -A2 semgrep_target_test services/knowledge_graph/BUILD
```

Expected output should show targets like:

```
semgrep_target_test(
    name = "scraper-image_semgrep_test",
    target = "//services/knowledge_graph/app:scraper",
```

**Step 3: Commit**

```bash
git add BUILD
git add -A  # all regenerated BUILD files
git commit -m "build(semgrep): add semgrep_target_kinds directive and regenerate BUILD files"
```

---

### Task 7: Push and verify CI

**Files:** None — CI verification only.

**Step 1: Push**

```bash
git push
```

**Step 2: Monitor CI**

Check `gh pr checks 708` or use BuildBuddy MCP tools to monitor the invocation.

Expected: Format check passes (gazelle regeneration is clean). Test and push passes (all semgrep tests run clean).

**Step 3: If CI fails, diagnose and fix**

Common failure modes:

- Missing `main` attr on converted `py_venv_binary` targets (already fixed in earlier commit)
- Stale BUILD files (re-run `format` and push)
- New `semgrep_target_test` targets fail because aspect doesn't collect expected files (check aspect.bzl changes)

# Semgrep Aspect Aggregation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace per-file semgrep tests with aspect-based tests that aggregate sources under binary targets, enabling meaningful `--pro` cross-file analysis.

**Architecture:** A Starlark aspect propagates through `deps` of `py_venv_binary`/`py_binary` targets, collecting transitive `.py` sources into a `depset`. A custom test rule applies this aspect and runs `semgrep-test.sh` on all collected files. The Gazelle extension is updated to detect binaries and generate target-based tests instead of per-file tests.

**Tech Stack:** Starlark (Bazel rules), Go (Gazelle extension), Bash (existing test runner)

---

### Task 1: Create the aspect and provider

**Files:**
- Create: `rules_semgrep/aspect.bzl`

**Step 1: Write the aspect**

Create `rules_semgrep/aspect.bzl`:

```starlark
"""Bazel aspect for collecting transitive Python sources for semgrep scanning."""

SemgrepSourcesInfo = provider(
    doc = "Carries transitive Python source files for semgrep scanning.",
    fields = {"sources": "depset of .py source files from the main repository"},
)

def _semgrep_source_aspect_impl(target, ctx):
    py_sources = []

    # Collect .py files from srcs attribute (py_library, py_binary)
    if hasattr(ctx.rule.attr, "srcs"):
        for src in ctx.rule.attr.srcs:
            for f in src.files.to_list():
                if f.extension == "py" and not f.short_path.startswith("../"):
                    py_sources.append(f)

    # Collect from main attribute (py_venv_binary, py_binary)
    if hasattr(ctx.rule.attr, "main"):
        main = ctx.rule.attr.main
        if main:
            main_targets = [main] if type(main) != "list" else main
            for m in main_targets:
                for f in m.files.to_list():
                    if f.extension == "py" and not f.short_path.startswith("../"):
                        py_sources.append(f)

    # Collect transitively from deps
    transitive = []
    if hasattr(ctx.rule.attr, "deps"):
        for dep in ctx.rule.attr.deps:
            if SemgrepSourcesInfo in dep:
                transitive.append(dep[SemgrepSourcesInfo].sources)

    return [SemgrepSourcesInfo(
        sources = depset(py_sources, transitive = transitive),
    )]

semgrep_source_aspect = aspect(
    implementation = _semgrep_source_aspect_impl,
    attr_aspects = ["deps"],
)
```

**Step 2: Commit**

```bash
git add rules_semgrep/aspect.bzl
git commit -m "feat(semgrep): add aspect for collecting transitive Python sources"
```

---

### Task 2: Create the test rule

**Files:**
- Create: `rules_semgrep/target_test.bzl`

**Context:** This rule applies `semgrep_source_aspect` to a target, collects all `.py` files from the `SemgrepSourcesInfo` provider, and generates a test script that invokes the existing `semgrep-test.sh`. The launcher script uses `short_path` references which work inside the Bazel test runner's runfiles tree.

**Step 1: Write the test rule**

Create `rules_semgrep/target_test.bzl`:

```starlark
"""Bazel test rule for running semgrep against a target's transitive Python sources."""

load("//rules_semgrep:aspect.bzl", "SemgrepSourcesInfo", "semgrep_source_aspect")

def _semgrep_target_test_impl(ctx):
    info = ctx.attr.target[SemgrepSourcesInfo]
    sources = info.sources.to_list()

    # Collect rule config files
    rule_files = []
    for rule_target in ctx.attr.rules:
        rule_files.extend(rule_target.files.to_list())

    # Build environment variable exports
    env_lines = []
    if ctx.attr.exclude_rules:
        env_lines.append("export SEMGREP_EXCLUDE_RULES=\"{}\"".format(
            ",".join(ctx.attr.exclude_rules),
        ))

    pro_file = None
    if ctx.attr.pro_engine:
        pro_files = ctx.attr.pro_engine.files.to_list()
        if pro_files:
            pro_file = pro_files[0]
            env_lines.append("export SEMGREP_PRO_ENGINE=\"{}\"".format(pro_file.short_path))

    # Build args for semgrep-test.sh
    semgrep = ctx.attr._semgrep[DefaultInfo].files_to_run.executable
    pysemgrep = ctx.attr._pysemgrep[DefaultInfo].files_to_run.executable
    test_runner = ctx.file._test_runner

    args = [semgrep.short_path, pysemgrep.short_path]
    args.extend([f.short_path for f in rule_files])
    args.append("--")
    args.extend([f.short_path for f in sources])

    # Write launcher script
    launcher = ctx.actions.declare_file(ctx.label.name + ".sh")
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    lines.extend(env_lines)

    if not sources:
        lines.append("echo 'No Python sources found in target dependency tree'")
        lines.append("exit 0")
    else:
        quoted_args = " ".join(["\"{}\"".format(a) for a in args])
        lines.append("exec \"{}\" {}".format(test_runner.short_path, quoted_args))

    ctx.actions.write(
        output = launcher,
        content = "\n".join(lines) + "\n",
        is_executable = True,
    )

    # Build runfiles — include all files the test needs at runtime
    all_files = [test_runner] + rule_files + sources
    if pro_file:
        all_files.append(pro_file)
    runfiles = ctx.runfiles(files = all_files)
    runfiles = runfiles.merge(ctx.attr._semgrep[DefaultInfo].default_runfiles)
    runfiles = runfiles.merge(ctx.attr._pysemgrep[DefaultInfo].default_runfiles)

    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

_semgrep_target_test = rule(
    implementation = _semgrep_target_test_impl,
    test = True,
    attrs = {
        "target": attr.label(
            aspects = [semgrep_source_aspect],
            mandatory = True,
            doc = "Target whose transitive Python sources will be scanned.",
        ),
        "rules": attr.label_list(
            allow_files = [".yaml"],
            mandatory = True,
            doc = "Semgrep rule config files or filegroups.",
        ),
        "exclude_rules": attr.string_list(
            doc = "Semgrep rule IDs to skip (matched against YAML filename).",
        ),
        "pro_engine": attr.label(
            allow_single_file = True,
            doc = "Label for semgrep-core-proprietary binary. Enables --pro flag.",
        ),
        "_test_runner": attr.label(
            default = "//rules_semgrep:semgrep-test.sh",
            allow_single_file = True,
        ),
        "_semgrep": attr.label(default = "//tools/semgrep"),
        "_pysemgrep": attr.label(default = "//tools/semgrep:pysemgrep"),
    },
)

def semgrep_target_test(name, target, rules, exclude_rules = [], pro_engine = None, **kwargs):
    """Creates a test that scans a target's transitive Python sources with semgrep.

    Uses an aspect to walk the target's dependency graph and collect all .py
    files from the main repository (excluding @pip// externals). Runs semgrep
    once on the full source closure, enabling meaningful --pro cross-file analysis.

    Args:
        name: Name of the test target.
        target: Label of the target to scan (e.g., a py_venv_binary).
        rules: Semgrep rule config files or filegroups.
        exclude_rules: List of semgrep rule IDs to skip.
        pro_engine: Optional label for semgrep-core-proprietary binary.
        **kwargs: Additional arguments passed to the test rule.
    """
    tags = kwargs.pop("tags", [])
    if "no-sandbox" not in tags:
        tags = tags + ["no-sandbox"]

    _semgrep_target_test(
        name = name,
        target = target,
        rules = rules,
        exclude_rules = exclude_rules,
        pro_engine = pro_engine,
        tags = tags,
        **kwargs
    )
```

**Step 2: Commit**

```bash
git add rules_semgrep/target_test.bzl
git commit -m "feat(semgrep): add target-based test rule with aspect"
```

---

### Task 3: Wire up BUILD and defs.bzl

**Files:**
- Modify: `rules_semgrep/BUILD`
- Modify: `rules_semgrep/defs.bzl`

**Step 1: Add bzl_library targets for aspect.bzl and target_test.bzl**

In `rules_semgrep/BUILD`, add after the existing `bzl_library` targets:

```starlark
bzl_library(
    name = "aspect",
    srcs = ["aspect.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "target_test",
    srcs = ["target_test.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        ":aspect",
        "@rules_shell//shell:rules_bzl",  # keep
    ],
)
```

Update the existing `defs` bzl_library to include the new files in its `deps`:

```starlark
bzl_library(
    name = "defs",
    srcs = [
        "defs.bzl",  # keep
        "test.bzl",  # keep
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":target_test",
        "@rules_shell//shell:rules_bzl",  # keep
    ],
)
```

**Step 2: Export semgrep_target_test from defs.bzl**

Update `rules_semgrep/defs.bzl`:

```starlark
"""Public API for rules_semgrep — Bazel rules for running semgrep scans."""

load("//rules_semgrep:target_test.bzl", _semgrep_target_test = "semgrep_target_test")
load("//rules_semgrep:test.bzl", _semgrep_manifest_test = "semgrep_manifest_test", _semgrep_test = "semgrep_test")

semgrep_test = _semgrep_test
semgrep_target_test = _semgrep_target_test
semgrep_manifest_test = _semgrep_manifest_test
```

**Step 3: Verify the build loads cleanly**

Run: `bazel build //rules_semgrep:defs`

Expected: BUILD SUCCESS (no analysis errors)

**Step 4: Commit**

```bash
git add rules_semgrep/BUILD rules_semgrep/defs.bzl
git commit -m "build(semgrep): wire up aspect and target_test in BUILD and defs"
```

---

### Task 4: Integration test — verify aspect works end-to-end

**Files:**
- Modify: `services/trips_api/BUILD` (temporary, manual test)

**Step 1: Manually add a semgrep_target_test to trips_api**

Add to `services/trips_api/BUILD` (after the existing `semgrep_test` targets):

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_target_test")

semgrep_target_test(
    name = "main_target_semgrep_test",
    target = ":main",
    rules = ["//semgrep_rules:python_rules"],
)
```

**Step 2: Run the test**

Run: `bazel test //services/trips_api:main_target_semgrep_test --test_output=all`

Expected: PASSED — semgrep scans `main.py` (and any transitive deps) with no violations.

**Step 3: Verify the aspect collected the right files**

Temporarily add a debug print to `aspect.bzl` at the end of `_semgrep_source_aspect_impl`:

```starlark
    result = depset(py_sources, transitive = transitive)
    # Debug: uncomment to see collected files during bazel build
    # print("SemgrepSourcesInfo for {}: {}".format(target.label, [f.short_path for f in result.to_list()]))
    return [SemgrepSourcesInfo(sources = result)]
```

Run: `bazel test //services/trips_api:main_target_semgrep_test --test_output=all 2>&1`

Verify that the test passes and scans `main.py`. If the debug print is enabled, check that `@pip//` files are NOT collected.

**Step 4: Revert the temporary changes to trips_api**

Remove the manually added `semgrep_target_test` from `services/trips_api/BUILD` (Gazelle will generate it later). Remove any debug prints from `aspect.bzl`.

**Step 5: Commit (if any fixes were needed)**

```bash
git add rules_semgrep/aspect.bzl rules_semgrep/target_test.bzl
git commit -m "fix(semgrep): adjust aspect/rule based on integration testing"
```

---

### Task 5: Update Gazelle extension — write failing tests first

**Files:**
- Modify: `rules_semgrep/gazelle/generate_test.go`

**Context:** The Gazelle extension at `rules_semgrep/gazelle/generate.go` currently generates one `semgrep_test` per `.py` file. We need to change it to detect `py_venv_binary`/`py_binary` targets and generate `semgrep_target_test` for each, falling back to per-file `semgrep_test` for orphan `.py` files not covered by a binary's `main`.

The test infrastructure uses `language.GenerateArgs` which provides `args.File` — the parsed BUILD file with access to existing rules via `args.File.Rules`. Each `rule.Rule` has `Kind()`, `Name()`, and `AttrString("main")` methods.

**Step 1: Write tests for binary detection**

Add to `rules_semgrep/gazelle/generate_test.go`:

```go
// helper to create a BUILD file with rules for testing
func buildFileWithRules(rules ...*rule.Rule) *rule.File {
	f, _ := rule.LoadData("BUILD", "", nil)
	for _, r := range rules {
		r.Insert(f)
	}
	return f
}

func newPyBinary(name, main string) *rule.Rule {
	r := rule.NewRule("py_venv_binary", name)
	r.SetAttr("main", main)
	return r
}

func newPyLibrary(name string, srcs []string) *rule.Rule {
	r := rule.NewRule("py_library", name)
	r.SetAttr("srcs", srcs)
	return r
}

func TestGenerateRules_WithBinary(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	binary := newPyBinary("main", "main.py")
	bf := buildFileWithRules(binary)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"__init__.py", "main.py", "utils.py"},
		File:         bf,
	}

	result := generateRules(args)

	// Expect: 1 semgrep_target_test for the binary + 2 per-file for orphans
	var targetTests, fileTests []*rule.Rule
	for _, r := range result.Gen {
		if r.Kind() == "semgrep_target_test" {
			targetTests = append(targetTests, r)
		} else {
			fileTests = append(fileTests, r)
		}
	}

	if len(targetTests) != 1 {
		t.Fatalf("expected 1 semgrep_target_test, got %d", len(targetTests))
	}
	if targetTests[0].AttrString("target") != ":main" {
		t.Errorf("target = %q, want %q", targetTests[0].AttrString("target"), ":main")
	}

	// Orphans: __init__.py and utils.py (main.py is covered by the binary)
	if len(fileTests) != 2 {
		t.Fatalf("expected 2 orphan semgrep_tests, got %d", len(fileTests))
	}
	assertRule(t, fileTests[0], "__init___semgrep_test", []string{"__init__.py"})
	assertRule(t, fileTests[1], "utils_semgrep_test", []string{"utils.py"})
}

func TestGenerateRules_MultipleBinaries(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	bf := buildFileWithRules(
		newPyBinary("scraper", "scraper_main.py"),
		newPyBinary("embedder", "embedder_main.py"),
	)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/kg/app",
		RegularFiles: []string{"__init__.py", "config.py", "embedder_main.py", "models.py", "scraper_main.py"},
		File:         bf,
	}

	result := generateRules(args)

	var targetTests, fileTests []*rule.Rule
	for _, r := range result.Gen {
		if r.Kind() == "semgrep_target_test" {
			targetTests = append(targetTests, r)
		} else {
			fileTests = append(fileTests, r)
		}
	}

	// 2 binary tests
	if len(targetTests) != 2 {
		t.Fatalf("expected 2 semgrep_target_tests, got %d", len(targetTests))
	}

	// Orphans: __init__.py, config.py, models.py (not main of any binary)
	if len(fileTests) != 3 {
		t.Fatalf("expected 3 orphan semgrep_tests, got %d", len(fileTests))
	}
}

func TestGenerateRules_NoBinaries_FallsBackToPerFile(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	// Package with only py_library, no binaries
	bf := buildFileWithRules(newPyLibrary("mylib", []string{"lib.py"}))

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "libs/shared",
		RegularFiles: []string{"lib.py", "helpers.py"},
		File:         bf,
	}

	result := generateRules(args)

	// All per-file (no binaries detected)
	for _, r := range result.Gen {
		if r.Kind() != "semgrep_test" {
			t.Errorf("expected all semgrep_test, got %q", r.Kind())
		}
	}
	if len(result.Gen) != 2 {
		t.Fatalf("expected 2 per-file tests, got %d", len(result.Gen))
	}
}

func TestGenerateRules_BinaryWithExcludeRules(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"no-requests"},
			},
		},
	}

	bf := buildFileWithRules(newPyBinary("main", "main.py"))

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py"},
		File:         bf,
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 rule, got %d", len(result.Gen))
	}
	if result.Gen[0].Attr("exclude_rules") == nil {
		t.Error("semgrep_target_test should have exclude_rules set")
	}
}

func TestGenerateRules_StaleTargetTestsRemoved(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	// Simulate a BUILD file that previously had a semgrep_target_test
	// that should now be removed (e.g., binary was deleted)
	oldTargetTest := rule.NewRule("semgrep_target_test", "old_semgrep_test")
	oldTargetTest.SetAttr("target", ":old_binary")
	bf := buildFileWithRules(oldTargetTest)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"main.py"},
		File:         bf,
	}

	result := generateRules(args)

	// Should mark old semgrep_target_test for removal
	foundStale := false
	for _, r := range result.Empty {
		if r.Kind() == "semgrep_target_test" && r.Name() == "old_semgrep_test" {
			foundStale = true
		}
	}
	if !foundStale {
		t.Error("expected stale semgrep_target_test to be marked for removal")
	}
}

func TestGenerateRules_PyBinaryKindAlsoDetected(t *testing.T) {
	c := &config.Config{Exts: make(map[string]interface{})}

	// py_binary (not py_venv_binary) should also trigger target-based tests
	r := rule.NewRule("py_binary", "main")
	r.SetAttr("main", "main.py")
	bf := buildFileWithRules(r)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "scripts",
		RegularFiles: []string{"main.py"},
		File:         bf,
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 rule, got %d", len(result.Gen))
	}
	if result.Gen[0].Kind() != "semgrep_target_test" {
		t.Errorf("expected semgrep_target_test, got %q", result.Gen[0].Kind())
	}
}
```

**Step 2: Run the tests to verify they fail**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=all`

Expected: FAIL — `generateRules` doesn't produce `semgrep_target_test` rules yet.

**Step 3: Commit**

```bash
git add rules_semgrep/gazelle/generate_test.go
git commit -m "test(semgrep): add failing tests for binary-based semgrep test generation"
```

---

### Task 6: Update Gazelle extension — implement generation logic

**Files:**
- Modify: `rules_semgrep/gazelle/generate.go`

**Step 1: Rewrite generateRules**

Replace the contents of `rules_semgrep/gazelle/generate.go`:

```go
package gazelle

import (
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// binaryKinds are the rule kinds that represent Python binary entry points.
var binaryKinds = map[string]bool{
	"py_venv_binary": true,
	"py_binary":      true,
}

// generateRules generates semgrep test targets for a package.
//
// When py_venv_binary or py_binary targets exist in the BUILD file:
//   - Generates one semgrep_target_test per binary (aspect scans transitive deps)
//   - Generates per-file semgrep_test for orphan .py files not covered by any binary's main
//
// When no binaries exist, falls back to per-file semgrep_test for every .py file.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	if !cfg.enabled {
		return result
	}

	pyFiles := pythonFiles(args.RegularFiles)
	if len(pyFiles) == 0 {
		result.Empty = staleRules(args, nil)
		return result
	}

	// Detect binary targets in the existing BUILD file
	binaries := findBinaries(args.File)

	if len(binaries) > 0 {
		// Collect main files covered by binaries
		coveredMains := make(map[string]bool)
		for _, b := range binaries {
			if main := b.AttrString("main"); main != "" {
				coveredMains[main] = true
			}
		}

		// Generate semgrep_target_test for each binary
		for _, b := range binaries {
			name := b.Name() + "_semgrep_test"
			r := rule.NewRule("semgrep_target_test", name)
			r.SetAttr("target", ":"+b.Name())
			r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}

		// Generate per-file semgrep_test for orphan .py files
		for _, f := range pyFiles {
			if coveredMains[f] {
				continue
			}
			name := strings.TrimSuffix(f, ".py") + "_semgrep_test"
			r := rule.NewRule("semgrep_test", name)
			r.SetAttr("srcs", []string{f})
			r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}
	} else {
		// No binaries — fall back to per-file semgrep_test
		for _, f := range pyFiles {
			name := strings.TrimSuffix(f, ".py") + "_semgrep_test"
			r := rule.NewRule("semgrep_test", name)
			r.SetAttr("srcs", []string{f})
			r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})
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

// findBinaries returns py_venv_binary and py_binary rules from the BUILD file.
func findBinaries(f *rule.File) []*rule.Rule {
	if f == nil {
		return nil
	}
	var binaries []*rule.Rule
	for _, r := range f.Rules {
		if binaryKinds[r.Kind()] {
			binaries = append(binaries, r)
		}
	}
	// Sort by name for deterministic output
	sort.Slice(binaries, func(i, j int) bool {
		return binaries[i].Name() < binaries[j].Name()
	})
	return binaries
}

// pythonFiles returns the sorted subset of files that end with .py.
func pythonFiles(files []string) []string {
	var py []string
	for _, f := range files {
		if strings.HasSuffix(f, ".py") {
			py = append(py, f)
		}
	}
	sort.Strings(py)
	return py
}

// staleRules returns empty rules for existing semgrep_test and semgrep_target_test
// rules not in the generated set.
func staleRules(args language.GenerateArgs, gen []*rule.Rule) []*rule.Rule {
	if args.File == nil {
		return nil
	}

	active := make(map[string]bool)
	for _, r := range gen {
		active[r.Kind()+"/"+r.Name()] = true
	}

	var empty []*rule.Rule
	for _, r := range args.File.Rules {
		kind := r.Kind()
		if (kind == "semgrep_test" || kind == "semgrep_target_test") && !active[kind+"/"+r.Name()] {
			empty = append(empty, rule.NewRule(kind, r.Name()))
		}
	}
	return empty
}

// sortedExcludeRules returns a sorted copy of the exclude rules list.
func sortedExcludeRules(rules []string) []string {
	sorted := append([]string{}, rules...)
	sort.Strings(sorted)
	return sorted
}
```

**Step 2: Run the tests**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=all`

Expected: All tests PASS (new tests and existing tests).

**Step 3: Commit**

```bash
git add rules_semgrep/gazelle/generate.go
git commit -m "feat(semgrep): generate target-based tests for binary packages"
```

---

### Task 7: Update Gazelle extension — register new kind and load

**Files:**
- Modify: `rules_semgrep/gazelle/language.go`

**Step 1: Add semgrep_target_test to Kinds()**

Update the `Kinds()` method in `rules_semgrep/gazelle/language.go`:

```go
func (l *semgrepLang) Kinds() map[string]rule.KindInfo {
	return map[string]rule.KindInfo{
		"semgrep_test": {
			MatchAny: false,
			NonEmptyAttrs: map[string]bool{
				"srcs":  true,
				"rules": true,
			},
			MergeableAttrs: map[string]bool{
				"exclude_rules": true,
			},
		},
		"semgrep_target_test": {
			MatchAny: false,
			NonEmptyAttrs: map[string]bool{
				"target": true,
				"rules":  true,
			},
			MergeableAttrs: map[string]bool{
				"exclude_rules": true,
			},
		},
	}
}
```

**Step 2: Add semgrep_target_test to Loads()**

Update the `Loads()` method:

```go
func (l *semgrepLang) Loads() []rule.LoadInfo {
	return []rule.LoadInfo{
		{
			Name:    "//rules_semgrep:defs.bzl",
			Symbols: []string{"semgrep_test", "semgrep_target_test"},
		},
	}
}
```

**Step 3: Update language_test.go for new kind**

In `rules_semgrep/gazelle/language_test.go`, update `TestSemgrepLang_Kinds`:

```go
func TestSemgrepLang_Kinds(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	expectedKinds := []string{"semgrep_test", "semgrep_target_test"}

	for _, k := range expectedKinds {
		if _, ok := kinds[k]; !ok {
			t.Errorf("Kinds() missing kind %q", k)
		}
	}
}
```

Update `TestSemgrepLang_Loads`:

```go
func TestSemgrepLang_Loads(t *testing.T) {
	lang := NewLanguage()
	loads := lang.Loads()

	if len(loads) != 1 {
		t.Fatalf("Loads() returned %d loads, want 1", len(loads))
	}

	load := loads[0]
	if load.Name != "//rules_semgrep:defs.bzl" {
		t.Errorf("Loads()[0].Name = %q, want %q", load.Name, "//rules_semgrep:defs.bzl")
	}

	expectedSymbols := map[string]bool{"semgrep_test": true, "semgrep_target_test": true}
	for _, s := range load.Symbols {
		delete(expectedSymbols, s)
	}
	for missing := range expectedSymbols {
		t.Errorf("defs.bzl should export %q symbol", missing)
	}
}
```

**Step 4: Run all gazelle tests**

Run: `bazel test //rules_semgrep/gazelle:gazelle_test --test_output=all`

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add rules_semgrep/gazelle/language.go rules_semgrep/gazelle/language_test.go
git commit -m "feat(semgrep): register semgrep_target_test kind in gazelle extension"
```

---

### Task 8: Run gazelle and verify regenerated BUILD files

**Step 1: Run format (which includes gazelle)**

Run: `format`

This runs gazelle which regenerates all BUILD files. Packages with `py_venv_binary`/`py_binary` targets will get `semgrep_target_test` instead of per-file `semgrep_test`.

**Step 2: Inspect a sample BUILD file**

Check `services/trips_api/BUILD`. Expected structure:

```starlark
semgrep_target_test(
    name = "main_semgrep_test",
    target = ":main",
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "trips_api_test_semgrep_test",
    srcs = ["trips_api_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

Check `services/knowledge_graph/app/BUILD`. Expected: 3 `semgrep_target_test` (scraper, embedder, mcp) + orphan per-file tests.

**Step 3: Run the full test suite**

Run: `bazel test //...`

Expected: All tests PASS. The new `semgrep_target_test` targets should pass (semgrep scans transitive sources with no violations).

**Step 4: Commit the regenerated BUILD files**

```bash
git add -A
git commit -m "build(semgrep): regenerate BUILD files with target-based semgrep tests"
```

---

### Task 9: Push and create PR

**Step 1: Push the branch**

```bash
git push -u origin feat/semgrep-aspect
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(semgrep): aggregate tests under binary targets via aspect" --body "$(cat <<'EOF'
## Summary
- Adds a Bazel aspect (`semgrep_source_aspect`) that propagates through `deps` of Python binary targets, collecting all transitive `.py` source files
- Adds `semgrep_target_test` rule that applies the aspect and runs semgrep on the full source closure, enabling meaningful `--pro` cross-file analysis
- Updates the Gazelle extension to detect `py_venv_binary`/`py_binary` targets and generate `semgrep_target_test` instead of per-file tests
- Orphan `.py` files (not a `main` of any binary) keep individual `semgrep_test` targets

Design doc: `docs/plans/2026-03-03-semgrep-aspect-aggregation-design.md`

## Test plan
- [ ] New Gazelle Go tests pass: `bazel test //rules_semgrep/gazelle:gazelle_test`
- [ ] Integration: `bazel test //services/trips_api:main_semgrep_test` passes with aspect-based scanning
- [ ] Full suite: `bazel test //...` passes with regenerated BUILD files
- [ ] Verify `knowledge_graph/app/BUILD` has 3 target tests + orphan per-file tests (down from 11)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

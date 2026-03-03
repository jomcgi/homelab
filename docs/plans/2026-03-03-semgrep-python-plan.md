# Python Semgrep Rules + Gazelle Extension Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add hermetic semgrep scanning for Python code with automatic BUILD target generation via a Gazelle extension.

**Architecture:** Five Python semgrep rules (security + conventions) in `semgrep_rules/python/`, auto-wired into every Python package by a new `rules_semgrep/gazelle/` Gazelle extension. The extension detects `*.py` files and emits `semgrep_test` rules; `format` (which calls `bazel run gazelle`) enforces their existence.

**Tech Stack:** Semgrep (YAML rules), Go (Gazelle extension), Bazel (build system), Starlark (BUILD files)

**Design doc:** `docs/plans/2026-03-03-semgrep-python-design.md`

---

### Task 1: Create Python semgrep rules and test fixtures

Create five semgrep rule YAML files and their companion `.py` test fixtures. Each fixture uses semgrep's `# ruleid:` and `# ok:` annotations to verify detection.

**Files:**
- Create: `semgrep_rules/python/no-shell-true.yaml`
- Create: `semgrep_rules/python/no-shell-true.py`
- Create: `semgrep_rules/python/no-os-system.yaml`
- Create: `semgrep_rules/python/no-os-system.py`
- Create: `semgrep_rules/python/no-eval-exec.yaml`
- Create: `semgrep_rules/python/no-eval-exec.py`
- Create: `semgrep_rules/python/no-requests.yaml`
- Create: `semgrep_rules/python/no-requests.py`
- Create: `semgrep_rules/python/no-hardcoded-secret.yaml`
- Create: `semgrep_rules/python/no-hardcoded-secret.py`

**Step 1: Create no-shell-true rule and fixture**

`semgrep_rules/python/no-shell-true.yaml`:
```yaml
rules:
  - id: no-shell-true
    languages: [python]
    severity: ERROR
    message: >-
      Do not use shell=True in subprocess calls — it enables command injection.
      Pass a list of arguments instead: subprocess.run(["cmd", "arg1", "arg2"]).
    metadata:
      category: security
    patterns:
      - pattern-either:
          - pattern: subprocess.run(..., shell=True, ...)
          - pattern: subprocess.call(..., shell=True, ...)
          - pattern: subprocess.Popen(..., shell=True, ...)
          - pattern: subprocess.check_call(..., shell=True, ...)
          - pattern: subprocess.check_output(..., shell=True, ...)
```

`semgrep_rules/python/no-shell-true.py`:
```python
import subprocess

# ruleid: no-shell-true
subprocess.run("ls -la", shell=True)

# ruleid: no-shell-true
subprocess.call("echo hello", shell=True)

# ruleid: no-shell-true
subprocess.Popen("cat /etc/passwd", shell=True)

# ruleid: no-shell-true
subprocess.check_call("rm -rf /tmp/test", shell=True)

# ruleid: no-shell-true
subprocess.check_output("whoami", shell=True)

# ok: no-shell-true
subprocess.run(["ls", "-la"])

# ok: no-shell-true
subprocess.run(["ls", "-la"], check=True)

# ok: no-shell-true
subprocess.Popen(["git", "status"])
```

**Step 2: Create no-os-system rule and fixture**

`semgrep_rules/python/no-os-system.yaml`:
```yaml
rules:
  - id: no-os-system
    languages: [python]
    severity: ERROR
    message: >-
      Do not use os.system() — it spawns a shell and enables command injection.
      Use subprocess.run() with a list of arguments instead.
    metadata:
      category: security
    pattern: os.system(...)
```

`semgrep_rules/python/no-os-system.py`:
```python
import os

# ruleid: no-os-system
os.system("ls -la")

# ruleid: no-os-system
os.system(f"rm -rf {path}")

# ok: no-os-system
os.path.exists("/tmp")

# ok: no-os-system
os.getenv("HOME")
```

**Step 3: Create no-eval-exec rule and fixture**

`semgrep_rules/python/no-eval-exec.yaml`:
```yaml
rules:
  - id: no-eval-exec
    languages: [python]
    severity: ERROR
    message: >-
      Do not use eval() or exec() — they run arbitrary code and are a
      security risk. Use safer alternatives like ast.literal_eval() for data
      parsing, or refactor to avoid dynamic code execution.
    metadata:
      category: security
    pattern-either:
      - pattern: eval(...)
      - pattern: exec(...)
```

`semgrep_rules/python/no-eval-exec.py`:
```python
import ast

# ruleid: no-eval-exec
eval("1 + 2")

# ruleid: no-eval-exec
eval(user_input)

# ruleid: no-eval-exec
exec("import os")

# ruleid: no-eval-exec
exec(code_string)

# ok: no-eval-exec
ast.literal_eval("{'key': 'value'}")

# ok: no-eval-exec
result = 1 + 2
```

**Step 4: Create no-requests rule and fixture**

`semgrep_rules/python/no-requests.yaml`:
```yaml
rules:
  - id: no-requests
    languages: [python]
    severity: WARNING
    message: >-
      Use httpx instead of requests for HTTP calls. httpx supports async/await
      which aligns with our FastAPI-based services. Install via @pip//httpx.
    metadata:
      category: best-practices
    pattern-either:
      - pattern: import requests
      - pattern: from requests import ...
```

`semgrep_rules/python/no-requests.py`:
```python
# ruleid: no-requests
import requests

# ruleid: no-requests
from requests import Session

# ok: no-requests
import httpx

# ok: no-requests
from httpx import AsyncClient
```

**Step 5: Create no-hardcoded-secret rule and fixture**

`semgrep_rules/python/no-hardcoded-secret.yaml`:
```yaml
rules:
  - id: no-hardcoded-secret
    languages: [python]
    severity: ERROR
    message: >-
      Do not hardcode secrets. Use environment variables via os.getenv() or
      pydantic-settings (BaseSettings with env_prefix). Secrets are injected
      at runtime by the 1Password Operator.
    metadata:
      category: security
    patterns:
      - pattern-either:
          - pattern: $VAR = "..."
          - pattern: $VAR = '...'
      - metavariable-regex:
          metavariable: $VAR
          regex: (?i)(password|secret|api_key|apikey|secret_key|private_key|auth_token)
      - pattern-not: $VAR = ""
```

`semgrep_rules/python/no-hardcoded-secret.py`:
```python
import os

# ruleid: no-hardcoded-secret
password = "hunter2"

# ruleid: no-hardcoded-secret
api_key = "CHANGE_ME"

# ruleid: no-hardcoded-secret
secret_key = "super-secret-value"

# ruleid: no-hardcoded-secret
auth_token = "bearer-token-value"

# ok: no-hardcoded-secret
password = ""

# ok: no-hardcoded-secret
api_key = os.getenv("API_KEY", "")

# ok: no-hardcoded-secret
username = "admin"

# ok: no-hardcoded-secret
database_url = "localhost:5432"
```

**Step 6: Commit**

```bash
git add semgrep_rules/python/
git commit -m "feat: add Python semgrep rules for security and conventions"
```

---

### Task 2: Add python_rules filegroup and rule validation test

Wire the new rules into `semgrep_rules/BUILD` and add a test that verifies each rule catches its fixtures.

**Files:**
- Modify: `semgrep_rules/BUILD`

**Step 1: Add python_rules filegroup to semgrep_rules/BUILD**

Add after the existing `kubernetes_rules` filegroup:

```starlark
filegroup(
    name = "python_rules",
    srcs = glob(["python/*.yaml"]),
)
```

**Step 2: Add a semgrep_test that validates rules catch fixtures**

Add a `semgrep_test` target that scans the Python fixture files against the Python rules. This verifies semgrep actually catches the patterns. Add to `semgrep_rules/BUILD`:

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_test")

semgrep_test(
    name = "python_rules_test",
    srcs = glob(["python/*.py"]),
    rules = [":python_rules"],
    tags = ["semgrep"],
)
```

**Step 3: Run the test to verify rules detect fixtures**

```bash
bazel test //semgrep_rules:python_rules_test
```

Expected: PASS — semgrep validates that `# ruleid:` annotations match actual findings and `# ok:` annotations produce no findings.

**Important:** If any rule doesn't match its fixture, semgrep will fail the test. Fix the YAML pattern until the test passes.

**Step 4: Commit**

```bash
git add semgrep_rules/BUILD
git commit -m "build: add python_rules filegroup and validation test"
```

---

### Task 3: Create Gazelle extension — config and generation

Create the `rules_semgrep/gazelle/` Go package following the exact pattern of `rules_helm/gazelle/`. This is the core logic.

**Reference files to read first:**
- `rules_helm/gazelle/config.go` — directive parsing pattern
- `rules_helm/gazelle/generate.go` — rule generation pattern
- `rules_helm/gazelle/language.go` — Language interface pattern
- `rules_helm/gazelle/BUILD` — go_library + go_test structure

**Files:**
- Create: `rules_semgrep/gazelle/config.go`
- Create: `rules_semgrep/gazelle/generate.go`
- Create: `rules_semgrep/gazelle/language.go`

**Step 1: Create config.go — directive parsing**

`rules_semgrep/gazelle/config.go`:

```go
package gazelle

import (
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// semgrepConfig holds configuration for the semgrep Gazelle extension.
type semgrepConfig struct {
	// enabled controls whether to generate semgrep_test rules in this directory
	enabled bool
	// excludeRules is a list of semgrep rule IDs to exclude (e.g., "no-requests")
	excludeRules []string
}

const semgrepConfigKey = "semgrep_config"

// getSemgrepConfig retrieves the semgrep configuration from a Bazel config.
func getSemgrepConfig(c *config.Config) *semgrepConfig {
	if cfg, ok := c.Exts[semgrepConfigKey].(*semgrepConfig); ok {
		return cfg
	}
	return &semgrepConfig{
		enabled: true,
	}
}

// configure reads semgrep-specific directives from BUILD files.
func configure(c *config.Config, rel string, f *rule.File) {
	parent := getSemgrepConfig(c)

	cfg := &semgrepConfig{
		enabled:      parent.enabled,
		excludeRules: append([]string{}, parent.excludeRules...),
	}

	if f != nil {
		for _, d := range f.Directives {
			switch d.Key {
			case "semgrep":
				// # gazelle:semgrep enabled
				// # gazelle:semgrep disabled
				cfg.enabled = d.Value != "disabled"

			case "semgrep_exclude_rules":
				// # gazelle:semgrep_exclude_rules no-requests,no-hardcoded-secret
				if d.Value != "" {
					cfg.excludeRules = strings.Split(d.Value, ",")
					for i, r := range cfg.excludeRules {
						cfg.excludeRules[i] = strings.TrimSpace(r)
					}
				}
			}
		}
	}

	c.Exts[semgrepConfigKey] = cfg
}
```

**Step 2: Create generate.go — Python file detection and rule generation**

`rules_semgrep/gazelle/generate.go`:

```go
package gazelle

import (
	"path/filepath"
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// generateRules generates semgrep_test rules for packages containing Python files.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	if !cfg.enabled {
		return result
	}

	if !hasPythonFiles(args.RegularFiles) {
		return result
	}

	r := rule.NewRule("semgrep_test", "semgrep_test")
	r.SetAttr("srcs", rule.GlobValue{
		Patterns: []string{"*.py"},
	})
	r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})

	if len(cfg.excludeRules) > 0 {
		r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
	}

	result.Gen = append(result.Gen, r)
	result.Imports = append(result.Imports, nil)

	return result
}

// hasPythonFiles checks if a list of filenames contains any .py files.
func hasPythonFiles(files []string) bool {
	for _, f := range files {
		if strings.HasSuffix(f, ".py") {
			return true
		}
	}
	return false
}

// sortedExcludeRules returns a sorted copy of exclude rules for deterministic output.
func sortedExcludeRules(rules []string) []string {
	sorted := append([]string{}, rules...)
	sort.Strings(sorted)
	return sorted
}

// unusedForCompiler prevents "imported and not used" for filepath.
var _ = filepath.Base
```

**Note:** The `filepath` import may not be needed in this simplified version. Remove the unused import guard and the import itself if the compiler is happy without it.

**Step 3: Create language.go — Language interface**

`rules_semgrep/gazelle/language.go`:

```go
package gazelle

import (
	"flag"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/repo"
	"github.com/bazelbuild/bazel-gazelle/resolve"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

const languageName = "semgrep"

// NewLanguage creates a new instance of the semgrep Gazelle language.
func NewLanguage() language.Language {
	return &semgrepLang{}
}

type semgrepLang struct{}

func (l *semgrepLang) Name() string {
	return languageName
}

func (l *semgrepLang) RegisterFlags(fs *flag.FlagSet, cmd string, c *config.Config) {}

func (l *semgrepLang) CheckFlags(fs *flag.FlagSet, c *config.Config) error {
	return nil
}

func (l *semgrepLang) KnownDirectives() []string {
	return []string{
		"semgrep",
		"semgrep_exclude_rules",
	}
}

func (l *semgrepLang) Configure(c *config.Config, rel string, f *rule.File) {
	configure(c, rel, f)
}

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
	}
}

func (l *semgrepLang) Loads() []rule.LoadInfo {
	return []rule.LoadInfo{
		{
			Name:    "//rules_semgrep:defs.bzl",
			Symbols: []string{"semgrep_test"},
		},
	}
}

func (l *semgrepLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
	return generateRules(args)
}

func (l *semgrepLang) Fix(c *config.Config, f *rule.File) {}

func (l *semgrepLang) Imports(c *config.Config, r *rule.Rule, f *rule.File) []resolve.ImportSpec {
	return nil
}

func (l *semgrepLang) Embeds(r *rule.Rule, from label.Label) []label.Label {
	return nil
}

func (l *semgrepLang) Resolve(c *config.Config, ix *resolve.RuleIndex, rc *repo.RemoteCache, r *rule.Rule, imports interface{}, from label.Label) {
}
```

**Step 4: Commit**

```bash
git add rules_semgrep/gazelle/config.go rules_semgrep/gazelle/generate.go rules_semgrep/gazelle/language.go
git commit -m "feat: add semgrep Gazelle extension for Python packages"
```

---

### Task 4: Create BUILD file and tests for Gazelle extension

Write the BUILD file and Go tests mirroring `rules_helm/gazelle/BUILD` and `*_test.go` patterns.

**Files:**
- Create: `rules_semgrep/gazelle/BUILD`
- Create: `rules_semgrep/gazelle/config_test.go`
- Create: `rules_semgrep/gazelle/generate_test.go`
- Create: `rules_semgrep/gazelle/language_test.go`

**Step 1: Create BUILD file**

`rules_semgrep/gazelle/BUILD`:

```starlark
load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "gazelle",
    srcs = [
        "config.go",
        "generate.go",
        "language.go",
    ],
    importpath = "github.com/jomcgi/homelab/rules_semgrep/gazelle",
    visibility = ["//:__pkg__"],
    deps = [
        "@gazelle//config",
        "@gazelle//label",
        "@gazelle//language",
        "@gazelle//repo",
        "@gazelle//resolve",
        "@gazelle//rule",
    ],
)

go_test(
    name = "gazelle_test",
    srcs = [
        "config_test.go",
        "generate_test.go",
        "language_test.go",
    ],
    embed = [":gazelle"],
    deps = [
        "@gazelle//config",
        "@gazelle//label",
        "@gazelle//language",
    ],
)
```

**Step 2: Create config_test.go**

`rules_semgrep/gazelle/config_test.go`:

```go
package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestGetSemgrepConfig_Defaults(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	cfg := getSemgrepConfig(c)

	if !cfg.enabled {
		t.Error("expected enabled to be true by default")
	}
	if len(cfg.excludeRules) != 0 {
		t.Errorf("expected empty excludeRules, got %v", cfg.excludeRules)
	}
}

func TestGetSemgrepConfig_FromExtension(t *testing.T) {
	expected := &semgrepConfig{
		enabled:      false,
		excludeRules: []string{"no-requests"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: expected,
		},
	}

	cfg := getSemgrepConfig(c)

	if cfg != expected {
		t.Error("expected to return the stored config")
	}
}

func TestConfigure_Directives(t *testing.T) {
	tests := []struct {
		name             string
		directives       []rule.Directive
		parentConfig     *semgrepConfig
		wantEnabled      bool
		wantExcludeRules []string
	}{
		{
			name:             "no directives uses defaults",
			directives:       nil,
			wantEnabled:      true,
			wantExcludeRules: nil,
		},
		{
			name: "semgrep disabled",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "disabled"},
			},
			wantEnabled:      false,
			wantExcludeRules: nil,
		},
		{
			name: "semgrep enabled",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "enabled"},
			},
			wantEnabled:      true,
			wantExcludeRules: nil,
		},
		{
			name: "exclude single rule",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "no-requests"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"no-requests"},
		},
		{
			name: "exclude multiple rules",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "no-requests, no-hardcoded-secret"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"no-requests", "no-hardcoded-secret"},
		},
		{
			name:       "inherits from parent",
			directives: nil,
			parentConfig: &semgrepConfig{
				enabled:      false,
				excludeRules: []string{"no-eval-exec"},
			},
			wantEnabled:      false,
			wantExcludeRules: []string{"no-eval-exec"},
		},
		{
			name: "child overrides parent exclude_rules",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "no-requests"},
			},
			parentConfig: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"no-eval-exec"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"no-requests"},
		},
		{
			name: "disabled with exclude rules",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "disabled"},
				{Key: "semgrep_exclude_rules", Value: "no-requests"},
			},
			wantEnabled:      false,
			wantExcludeRules: []string{"no-requests"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			c := &config.Config{
				Exts: make(map[string]interface{}),
			}

			if tc.parentConfig != nil {
				c.Exts[semgrepConfigKey] = tc.parentConfig
			}

			var f *rule.File
			if tc.directives != nil {
				f = &rule.File{
					Directives: tc.directives,
				}
			}

			configure(c, "", f)

			cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

			if cfg.enabled != tc.wantEnabled {
				t.Errorf("enabled: got %v, want %v", cfg.enabled, tc.wantEnabled)
			}

			if len(cfg.excludeRules) != len(tc.wantExcludeRules) {
				t.Errorf("excludeRules: got %v, want %v", cfg.excludeRules, tc.wantExcludeRules)
			} else {
				for i, r := range cfg.excludeRules {
					if r != tc.wantExcludeRules[i] {
						t.Errorf("excludeRules[%d]: got %q, want %q", i, r, tc.wantExcludeRules[i])
					}
				}
			}
		})
	}
}

func TestConfigure_NilFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	configure(c, "some/rel/path", nil)

	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if !cfg.enabled {
		t.Error("expected enabled to be true with nil file")
	}
}
```

**Step 3: Create generate_test.go**

`rules_semgrep/gazelle/generate_test.go`:

```go
package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
)

func TestGenerateRules_PythonFiles(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{enabled: true},
			},
		},
		Rel:          "services/trips_api",
		RegularFiles: []string{"main.py", "models.py", "BUILD"},
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

	rules := r.AttrStrings("rules")
	if len(rules) != 1 || rules[0] != "//semgrep_rules:python_rules" {
		t.Errorf("rules = %v, want [//semgrep_rules:python_rules]", rules)
	}

	if r.Attr("exclude_rules") != nil {
		t.Error("expected no exclude_rules attribute")
	}
}

func TestGenerateRules_NoPythonFiles(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{enabled: true},
			},
		},
		Rel:          "charts/todo",
		RegularFiles: []string{"Chart.yaml", "values.yaml", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules for non-Python package, got %d", len(result.Gen))
	}
}

func TestGenerateRules_Disabled(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{enabled: false},
			},
		},
		Rel:          "services/trips_api",
		RegularFiles: []string{"main.py"},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules when disabled, got %d", len(result.Gen))
	}
}

func TestGenerateRules_WithExcludeRules(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{
					enabled:      true,
					excludeRules: []string{"no-requests", "no-hardcoded-secret"},
				},
			},
		},
		Rel:          "services/hikes/scrape_walkhighlands",
		RegularFiles: []string{"scrape.py", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule, got %d", len(result.Gen))
	}

	r := result.Gen[0]
	excludeRules := r.AttrStrings("exclude_rules")
	if len(excludeRules) != 2 {
		t.Fatalf("expected 2 exclude_rules, got %d: %v", len(excludeRules), excludeRules)
	}
}

func TestGenerateRules_MixedFiles(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{enabled: true},
			},
		},
		Rel:          "scripts",
		RegularFiles: []string{"deploy.sh", "helper.py", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 1 {
		t.Fatalf("expected 1 generated rule (Python found), got %d", len(result.Gen))
	}
}

func TestGenerateRules_OnlyNonPythonFiles(t *testing.T) {
	args := language.GenerateArgs{
		Config: &config.Config{
			Exts: map[string]interface{}{
				semgrepConfigKey: &semgrepConfig{enabled: true},
			},
		},
		Rel:          "scripts",
		RegularFiles: []string{"deploy.sh", "format.sh", "BUILD"},
	}

	result := generateRules(args)

	if len(result.Gen) != 0 {
		t.Errorf("expected 0 generated rules for shell-only package, got %d", len(result.Gen))
	}
}

func TestHasPythonFiles(t *testing.T) {
	tests := []struct {
		name  string
		files []string
		want  bool
	}{
		{"python files", []string{"main.py", "util.py"}, true},
		{"mixed files", []string{"main.go", "helper.py"}, true},
		{"no python", []string{"main.go", "deploy.sh"}, false},
		{"empty", []string{}, false},
		{"py in name but not extension", []string{"python_config.yaml"}, false},
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
```

**Step 4: Create language_test.go**

`rules_semgrep/gazelle/language_test.go`:

```go
package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/label"
)

func TestNewLanguage(t *testing.T) {
	lang := NewLanguage()
	if lang == nil {
		t.Fatal("NewLanguage() returned nil")
	}

	_, ok := lang.(*semgrepLang)
	if !ok {
		t.Error("NewLanguage() should return *semgrepLang")
	}
}

func TestSemgrepLang_Name(t *testing.T) {
	lang := NewLanguage()

	if name := lang.Name(); name != "semgrep" {
		t.Errorf("Name() = %q, want %q", name, "semgrep")
	}
}

func TestSemgrepLang_KnownDirectives(t *testing.T) {
	lang := NewLanguage()
	directives := lang.KnownDirectives()

	expected := map[string]bool{
		"semgrep":               true,
		"semgrep_exclude_rules": true,
	}

	if len(directives) != len(expected) {
		t.Errorf("KnownDirectives() returned %d, want %d", len(directives), len(expected))
	}

	for _, d := range directives {
		if !expected[d] {
			t.Errorf("unexpected directive %q", d)
		}
	}
}

func TestSemgrepLang_Kinds(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	semgrepTest, ok := kinds["semgrep_test"]
	if !ok {
		t.Fatal("Kinds() missing semgrep_test")
	}

	if !semgrepTest.NonEmptyAttrs["srcs"] {
		t.Error("semgrep_test should have srcs as non-empty attr")
	}
	if !semgrepTest.NonEmptyAttrs["rules"] {
		t.Error("semgrep_test should have rules as non-empty attr")
	}
	if !semgrepTest.MergeableAttrs["exclude_rules"] {
		t.Error("semgrep_test should have exclude_rules as mergeable attr")
	}
}

func TestSemgrepLang_Loads(t *testing.T) {
	lang := NewLanguage()
	loads := lang.Loads()

	if len(loads) != 1 {
		t.Fatalf("Loads() returned %d, want 1", len(loads))
	}

	if loads[0].Name != "//rules_semgrep:defs.bzl" {
		t.Errorf("load name = %q, want %q", loads[0].Name, "//rules_semgrep:defs.bzl")
	}

	found := false
	for _, s := range loads[0].Symbols {
		if s == "semgrep_test" {
			found = true
		}
	}
	if !found {
		t.Error("load should export semgrep_test symbol")
	}
}

func TestSemgrepLang_CheckFlags(t *testing.T) {
	lang := NewLanguage()
	if err := lang.CheckFlags(nil, nil); err != nil {
		t.Errorf("CheckFlags() returned error: %v", err)
	}
}

func TestSemgrepLang_Imports(t *testing.T) {
	lang := NewLanguage()
	if imports := lang.Imports(nil, nil, nil); imports != nil {
		t.Errorf("Imports() should return nil, got %v", imports)
	}
}

func TestSemgrepLang_Embeds(t *testing.T) {
	lang := &semgrepLang{}
	if embeds := lang.Embeds(nil, label.Label{}); embeds != nil {
		t.Errorf("Embeds() should return nil, got %v", embeds)
	}
}
```

**Step 5: Run tests**

```bash
bazel test //rules_semgrep/gazelle:gazelle_test
```

Expected: PASS

**Step 6: Commit**

```bash
git add rules_semgrep/gazelle/
git commit -m "test: add Gazelle extension tests for semgrep Python scanning"
```

---

### Task 5: Wire Gazelle extension into root BUILD

Add the semgrep extension to the `gazelle_binary` and enable it.

**Files:**
- Modify: `BUILD` (root) — add to `gazelle_binary` languages and `ENABLE_LANGUAGES`

**Step 1: Add to gazelle_binary languages**

In root `BUILD`, add `"//rules_semgrep/gazelle"` to the `languages` list:

```starlark
gazelle_binary(
    name = "gazelle_binary",
    languages = [
        "//rules_helm/gazelle",
        "//rules_wrangler/gazelle",
        "//rules_semgrep/gazelle",
        "@bazel_skylib_gazelle_plugin//bzl",
        "@gazelle//language/go",
        "@gazelle//language/proto",
        "@rules_python_gazelle_plugin//python",
    ],
)
```

**Step 2: Add "semgrep" to ENABLE_LANGUAGES**

```starlark
gazelle(
    name = "gazelle",
    env = {
        "ENABLE_LANGUAGES": ",".join([
            "argocd",
            "wrangler",
            "semgrep",
            "bzl",
            "proto",
            "go",
            "python",
        ]),
    },
    gazelle = ":gazelle_binary",
)
```

**Step 3: Commit**

```bash
git add BUILD
git commit -m "build: wire semgrep Gazelle extension into gazelle_binary"
```

---

### Task 6: Add exclusion directives and run gazelle

Add `# gazelle:semgrep disabled` to fixture directories and `# gazelle:semgrep_exclude_rules` to services that legitimately use excluded patterns. Then run gazelle to auto-generate all targets.

**Files:**
- Modify: `semgrep_rules/BUILD` — add `# gazelle:semgrep disabled`
- Modify: `services/hikes/scrape_walkhighlands/BUILD` — add `# gazelle:semgrep_exclude_rules no-requests`
- Modify: `services/hikes/update_forecast/BUILD` — add `# gazelle:semgrep_exclude_rules no-requests`
- Many service BUILD files auto-modified by gazelle

**Step 1: Add semgrep disabled to semgrep_rules/BUILD**

Add at top of `semgrep_rules/BUILD`:
```
# gazelle:semgrep disabled
```

**Step 2: Add exclusion for hikes services**

Add to `services/hikes/scrape_walkhighlands/BUILD`:
```
# gazelle:semgrep_exclude_rules no-requests
```

Add to `services/hikes/update_forecast/BUILD`:
```
# gazelle:semgrep_exclude_rules no-requests
```

**Step 3: Run gazelle**

```bash
bazel run //:gazelle
```

This auto-generates `semgrep_test` targets in every Python package BUILD file.

**Step 4: Verify generated targets**

```bash
grep -rl "semgrep_test" services/ scripts/ advent_of_code/
```

Expected: BUILD files for all Python packages should now have `semgrep_test` targets.

**Step 5: Run all tests**

```bash
bazel test //...
```

Expected: All tests PASS. If any Python file legitimately violates a rule, either fix the code or add an `exclude_rules` directive.

**Step 6: Commit**

```bash
git add .
git commit -m "feat: auto-generate Python semgrep_test targets via gazelle"
```

---

### Task 7: Run format and verify end-to-end

Verify the full developer workflow works end-to-end.

**Step 1: Run format**

```bash
bazel run //tools/format
```

Verify no diff after running (gazelle should already be in sync).

**Step 2: Run full test suite**

```bash
bazel test //...
```

Expected: All tests PASS.

**Step 3: Commit formatting changes (if any)**

```bash
git add -A && git diff --cached --quiet || git commit -m "style: apply formatting from format run"
```

---

### Task 8: Create pull request

**Step 1: Push branch**

```bash
git push -u origin feat/semgrep-python
```

**Step 2: Create PR**

Use `gh pr create` with the title "feat: Python semgrep rules with Gazelle auto-generation" and a body summarizing:
- 5 Python semgrep rules (3 security, 2 conventions)
- Gazelle extension for auto-generating `semgrep_test` targets
- Directive-based opt-out (`# gazelle:semgrep disabled`, `# gazelle:semgrep_exclude_rules`)
- Test plan: rule fixture validation, Gazelle Go unit tests, full `bazel test //...`

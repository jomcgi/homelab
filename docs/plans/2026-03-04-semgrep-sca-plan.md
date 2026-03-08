# Semgrep SCA Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Software Composition Analysis (SCA) to rules_semgrep, enabling lockfile-based vulnerability scanning with reachability analysis in a single Bazel test invocation alongside SAST.

**Architecture:** Extend `semgrep_target_test` and `semgrep_test` with optional `lockfiles` and `sca_rules` attributes. The test script generates semgrep-core `targets.json` with `products: ["sast", "sca"]` and `dependency_source` when lockfiles are present. SCA advisory rules are vendored as OCI artifacts on GHCR. Gazelle auto-detects lockfiles by inspecting target deps for `@pip//`, `@npm//`, and Go module prefixes.

**Tech Stack:** Starlark (Bazel rules), Bash (test script), Go (Gazelle extension), YAML (SCA rules), GitHub Actions (update workflow)

**Design doc:** `docs/plans/2026-03-04-semgrep-sca-design.md`

---

### Task 1: Add SCA Rule Vendoring Infrastructure

Add the OCI artifact definition for SCA advisory rules, following the existing Pro rule pack pattern.

**Files:**

- Modify: `third_party/semgrep_pro/digests.bzl:7-16` — add `rules_sca` digest entry
- Modify: `third_party/semgrep_pro/extensions.bzl:47-54` — add `semgrep_sca_rules` OCI archive
- Modify: `MODULE.bazel:209-220` — register `semgrep_sca_rules` repo
- Modify: `semgrep_rules/BUILD:1-63` — add `sca_rules` filegroup

**Step 1: Add empty SCA digest**

In `third_party/semgrep_pro/digests.bzl`, add an entry for SCA rules with an empty digest (will be populated when the first OCI artifact is pushed):

```python
SEMGREP_PRO_DIGESTS = {
    # ... existing entries ...
    "rules_sca": "",
}
```

**Step 2: Add OCI archive for SCA rules**

In `third_party/semgrep_pro/extensions.bzl`, add after the language rule pack loop (line 54):

```starlark
    # SCA advisory rules — vendored from Semgrep registry
    oci_archive(
        name = "semgrep_sca_rules",
        image = _GHCR_PREFIX + "/rules-sca",
        digest = SEMGREP_PRO_DIGESTS.get("rules_sca", ""),
        build_file_content = _RULES_BUILD,
    )
```

**Step 3: Register SCA rules repo in MODULE.bazel**

Add `"semgrep_sca_rules"` to the `use_repo(semgrep_pro, ...)` call:

```starlark
use_repo(
    semgrep_pro,
    # ... existing entries ...
    "semgrep_sca_rules",
)
```

**Step 4: Add sca_rules filegroup**

In `semgrep_rules/BUILD`, add:

```starlark
filegroup(
    name = "sca_rules",
    srcs = ["@semgrep_sca_rules//:rules"],
)
```

**Step 5: Verify build**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel build //semgrep_rules:sca_rules`
Expected: BUILD SUCCESS (empty filegroup since digest is empty — graceful degradation)

**Step 6: Commit**

```bash
git add third_party/semgrep_pro/digests.bzl third_party/semgrep_pro/extensions.bzl MODULE.bazel semgrep_rules/BUILD
git commit -m "feat(semgrep): add SCA rule vendoring infrastructure"
```

---

### Task 2: Extend semgrep_target_test with Lockfile Attributes

Add optional `lockfiles` and `sca_rules` attributes to the `semgrep_target_test` rule, passing them through to the test script.

**Files:**

- Modify: `rules_semgrep/target_test.bzl:1-122`

**Step 1: Add attributes to the rule definition**

In `_semgrep_target_test` rule (line 65), add new attrs after `exclude_rules`:

```starlark
        "lockfiles": attr.label_list(
            allow_files = True,
            doc = "Lockfile(s) for SCA dependency scanning (e.g., go.sum, requirements.txt).",
        ),
        "sca_rules": attr.label_list(
            allow_files = [".yaml"],
            doc = "SCA advisory rule config files or filegroups.",
        ),
```

**Step 2: Update the implementation to pass lockfiles**

In `_semgrep_target_test_impl` (line 5), after collecting rule files, collect lockfile and SCA rule files:

```starlark
    # Collect lockfile files
    lockfile_files = []
    for lf_target in ctx.attr.lockfiles:
        lockfile_files.extend(lf_target.files.to_list())

    # Collect SCA rule files
    sca_rule_files = []
    for sca_target in ctx.attr.sca_rules:
        sca_rule_files.extend(sca_target.files.to_list())
```

Update the args to include SCA rules in the rule section and lockfiles after a second `--`:

```starlark
    # Build args: <rule-files> <sca-rule-files> -- <source-files> [-- <lockfile-files>]
    args = [f.short_path for f in rule_files + sca_rule_files]
    args.append("--")
    args.extend([f.short_path for f in sources])
    if lockfile_files:
        args.append("--")
        args.extend([f.short_path for f in lockfile_files])
```

Update `all_files` to include lockfile and SCA rule files in runfiles:

```starlark
    all_files = [test_runner] + rule_files + sca_rule_files + sources + lockfile_files + engine_files + pro_files
```

**Step 3: Update the macro signature**

In `semgrep_target_test` def (line 94), add the new parameters:

```starlark
def semgrep_target_test(name, target, rules, lockfiles = [], sca_rules = [], exclude_rules = [], pro_engine = "//third_party/semgrep_pro:engine", **kwargs):
```

Pass them through to the rule:

```starlark
    _semgrep_target_test(
        name = name,
        target = target,
        rules = rules,
        lockfiles = lockfiles,
        sca_rules = sca_rules,
        exclude_rules = exclude_rules,
        pro_engine = pro_engine,
        tags = tags,
        **kwargs
    )
```

**Step 4: Verify build**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel build //rules_semgrep:target_test`
Expected: BUILD SUCCESS

**Step 5: Commit**

```bash
git add rules_semgrep/target_test.bzl
git commit -m "feat(semgrep): add lockfiles and sca_rules attrs to semgrep_target_test"
```

---

### Task 3: Extend semgrep_test with Lockfile Attributes

Add the same optional `lockfiles` and `sca_rules` attributes to the `semgrep_test` macro.

**Files:**

- Modify: `rules_semgrep/test.bzl:5-59`

**Step 1: Update semgrep_test macro**

Add `lockfiles = []` and `sca_rules = []` parameters to the macro (line 5). Update the `data` and `args` to include them:

```starlark
def semgrep_test(
        name,
        srcs,
        rules,
        lockfiles = [],
        sca_rules = [],
        exclude_rules = [],
        pro_engine = "//third_party/semgrep_pro:engine",
        **kwargs):
```

Update `data`:

```starlark
    data = [
        "//third_party/semgrep:engine",
        "//tools/semgrep:upload",
    ] + rules + sca_rules + srcs + lockfiles
```

Update `args` to add lockfiles after a second `--`:

```starlark
    rule_args = ["$(rootpaths {})".format(r) for r in rules + sca_rules]
    src_args = ["$(rootpaths {})".format(s) for s in srcs]
    lockfile_args = ["$(rootpaths {})".format(lf) for lf in lockfiles] if lockfiles else []

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = rule_args + ["--"] + src_args + (["--"] + lockfile_args if lockfile_args else []),
        data = data,
        env = env,
        tags = tags,
        **kwargs
    )
```

**Step 2: Verify build**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel build //rules_semgrep:defs`
Expected: BUILD SUCCESS

**Step 3: Commit**

```bash
git add rules_semgrep/test.bzl
git commit -m "feat(semgrep): add lockfiles and sca_rules attrs to semgrep_test"
```

---

### Task 4: Update Test Script for SCA Support

Extend `semgrep-test.sh` to handle lockfiles and generate SCA-aware `targets.json`.

**Files:**

- Modify: `rules_semgrep/semgrep-test.sh`

**Step 1: Add lockfile kind detection function**

After `detect_lang()` (line 131), add:

```bash
# Map lockfile filename to semgrep-core lockfile_kind enum
detect_lockfile_kind() {
    local basename
    basename="$(basename "$1")"
    case "$basename" in
    go.sum)              echo "GoModLock" ;;
    requirements*.txt|requirements*.pip) echo "PipRequirementsTxt" ;;
    poetry.lock)         echo "PoetryLock" ;;
    Pipfile.lock)        echo "PipfileLock" ;;
    uv.lock)             echo "UvLock" ;;
    package-lock.json)   echo "NpmPackageLockJson" ;;
    yarn.lock)           echo "YarnLock" ;;
    pnpm-lock.yaml)      echo "PnpmLock" ;;
    *)                   echo "" ;;
    esac
}
```

**Step 2: Parse lockfiles from a second -- separator**

After parsing source files (after `shift # skip --` on line 88), add:

```bash
# Collect source files until we hit another -- separator (or end of args)
SOURCE_ARGS=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
    SOURCE_ARGS+=("$1")
    shift
done

# Collect lockfile files after the optional second --
LOCKFILE_ARGS=()
if [[ $# -gt 0 && "$1" == "--" ]]; then
    shift  # skip second --
    LOCKFILE_ARGS=("$@")
fi
```

This replaces the current logic where `$@` is used directly for source files.

**Step 3: Copy lockfiles to scan directory**

After copying source files to the scan directory, add:

```bash
# Copy lockfile files to scan directory
LOCKFILE_FILES=()
for f in "${LOCKFILE_ARGS[@]}"; do
    mkdir -p "$SCAN_DIR/$(dirname "$f")"
    cp "$f" "$SCAN_DIR/$f"
    LOCKFILE_FILES+=("$SCAN_DIR/$f")
done
```

**Step 4: Update targets.json generation for SCA**

Modify the targets.json generation (line 136) to include SCA products and dependency_source when lockfiles are present:

```bash
# Determine products and dependency_source based on lockfiles
HAS_LOCKFILES=false
LOCKFILE_JSON=""
if [[ ${#LOCKFILE_FILES[@]} -gt 0 ]]; then
    HAS_LOCKFILES=true
    # Use the first lockfile for dependency_source (semgrep deduplicates internally)
    LF="${LOCKFILE_FILES[0]}"
    LF_KIND=$(detect_lockfile_kind "$LF")
    if [[ -n "$LF_KIND" ]]; then
        LF_ABS="$(cd "$(dirname "$LF")" && pwd)/$(basename "$LF")"
        LOCKFILE_JSON=$(printf ',"dependency_source":["LockfileOnly",{"kind":"%s","path":"%s"}]' "$LF_KIND" "$LF_ABS")
    fi
fi

PRODUCTS='["sast"]'
if [[ "$HAS_LOCKFILES" == "true" ]]; then
    PRODUCTS='["sast","sca"]'
fi

# Generate targets JSON
TARGETS_FILE="${TEST_TMPDIR}/targets.json"
{
    echo -n '["Targets",['
    first=true

    # CodeTargets for source files
    for f in "${SOURCE_FILES[@]}"; do
        lang=$(detect_lang "$f")
        if [[ -z "$lang" ]]; then
            continue
        fi
        abs_path="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
        if [[ "$first" == "true" ]]; then
            first=false
        else
            echo -n ','
        fi
        echo -n "$(printf '["CodeTarget",{"path":{"fpath":"%s","ppath":"%s"},"analyzer":"%s","products":%s%s}]' \
            "$abs_path" "$abs_path" "$lang" "$PRODUCTS" "$LOCKFILE_JSON")"
    done

    # DependencySourceTargets for lockfile-only mode (no source files)
    if [[ ${#SOURCE_FILES[@]} -eq 0 && "$HAS_LOCKFILES" == "true" ]]; then
        for lf in "${LOCKFILE_FILES[@]}"; do
            lf_kind=$(detect_lockfile_kind "$lf")
            if [[ -z "$lf_kind" ]]; then
                continue
            fi
            lf_abs="$(cd "$(dirname "$lf")" && pwd)/$(basename "$lf")"
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo -n ','
            fi
            echo -n "$(printf '["DependencySourceTarget",["LockfileOnly",{"kind":"%s","path":"%s"}]]' "$lf_kind" "$lf_abs")"
        done
    fi

    echo ']]'
} >"$TARGETS_FILE"
```

**Step 5: Test locally**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //tools/semgrep:semgrep_test`
Expected: PASS (existing SAST test still works with no lockfiles)

**Step 6: Commit**

```bash
git add rules_semgrep/semgrep-test.sh
git commit -m "feat(semgrep): add SCA lockfile support to test script"
```

---

### Task 5: Extend Gazelle with Dep Prefix Lockfile Detection

Add SCA lockfile auto-detection to the Gazelle extension via dep prefix matching.

**Files:**

- Modify: `rules_semgrep/gazelle/config.go` — add SCA config fields and directives
- Modify: `rules_semgrep/gazelle/generate.go` — add dep inspection and lockfile attachment
- Modify: `rules_semgrep/gazelle/language.go` — register new directives and mergeable attrs
- Create: `rules_semgrep/gazelle/sca.go` — dep prefix to lockfile mapping logic

**Step 1: Write failing tests for SCA config parsing**

In `rules_semgrep/gazelle/config_test.go`, add tests for the new SCA directives:

```go
func TestConfigure_SCADirectives(t *testing.T) {
    c := &config.Config{
        Exts: make(map[string]interface{}),
    }

    f := &rule.File{
        Directives: []rule.Directive{
            {Key: "semgrep_sca", Value: "disabled"},
        },
    }

    configure(c, "", f)
    cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

    if cfg.scaEnabled {
        t.Error("expected scaEnabled to be false after disabled directive")
    }
}

func TestConfigure_SCALockfileDirective(t *testing.T) {
    c := &config.Config{
        Exts: make(map[string]interface{}),
    }

    f := &rule.File{
        Directives: []rule.Directive{
            {Key: "semgrep_lockfile", Value: "pip //requirements:custom.txt"},
        },
    }

    configure(c, "", f)
    cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

    if cfg.lockfiles["pip"] != "//requirements:custom.txt" {
        t.Errorf("expected pip lockfile override, got %q", cfg.lockfiles["pip"])
    }
}
```

**Step 2: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //rules_semgrep/gazelle:gazelle_test`
Expected: FAIL (scaEnabled and lockfiles fields don't exist yet)

**Step 3: Add SCA config fields**

In `rules_semgrep/gazelle/config.go`, add to `semgrepConfig`:

```go
type semgrepConfig struct {
    // ... existing fields ...
    // scaEnabled controls whether to generate SCA lockfile attrs
    scaEnabled bool
    // scaRules is the label for SCA advisory rules
    scaRules string
    // lockfiles maps dep ecosystem to lockfile label
    lockfiles map[string]string
}
```

Update defaults in `getSemgrepConfig`:

```go
return &semgrepConfig{
    // ... existing defaults ...
    scaEnabled: true,
    scaRules:   "//semgrep_rules:sca_rules",
    lockfiles:  copyLockfiles(defaultLockfiles),
}
```

Add `defaultLockfiles`:

```go
var defaultLockfiles = map[string]string{
    "pip":   "//requirements:all.txt",
    "pnpm":  "//:pnpm-lock.yaml",
    "gomod": "//:go.sum",
}
```

Add directive handling in `configure()`:

```go
case "semgrep_sca":
    cfg.scaEnabled = d.Value != "disabled"
case "semgrep_sca_rules":
    if d.Value != "" {
        cfg.scaRules = d.Value
    }
case "semgrep_lockfile":
    // Format: "ecosystem label" e.g. "pip //requirements:all.txt"
    parts := strings.SplitN(d.Value, " ", 2)
    if len(parts) == 2 {
        cfg.lockfiles[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
    }
```

Add clone logic for lockfiles in `configure()` and a `copyLockfiles` helper.

**Step 4: Run tests to verify config tests pass**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //rules_semgrep/gazelle:gazelle_test`
Expected: Config tests PASS

**Step 5: Write failing tests for lockfile generation**

In `rules_semgrep/gazelle/generate_test.go`, add:

```go
func TestGenerateRules_WithBinaryAndPipDeps(t *testing.T) {
    c := &config.Config{
        Exts: map[string]interface{}{
            semgrepConfigKey: &semgrepConfig{
                enabled:     true,
                scaEnabled:  true,
                scaRules:    "//semgrep_rules:sca_rules",
                lockfiles:   map[string]string{"pip": "//requirements:all.txt"},
                targetKinds: map[string]string{"py_venv_binary": ""},
                languages:   []string{"py"},
            },
        },
    }

    binary := newPyBinaryWithDeps("server", "server.py", []string{"@pip//requests", ":utils"})
    buildFile := buildFileWithRules(binary)

    args := language.GenerateArgs{
        Config:       c,
        Dir:          "/tmp/test",
        Rel:          "services/myapp",
        RegularFiles: []string{"server.py"},
        File:         buildFile,
    }

    result := generateRules(args)

    if len(result.Gen) < 1 {
        t.Fatalf("expected at least 1 rule, got %d", len(result.Gen))
    }

    targetRule := result.Gen[0]
    if targetRule.Kind() != "semgrep_target_test" {
        t.Fatalf("rule[0] kind = %q, want semgrep_target_test", targetRule.Kind())
    }

    lockfiles := targetRule.AttrStrings("lockfiles")
    if len(lockfiles) != 1 || lockfiles[0] != "//requirements:all.txt" {
        t.Errorf("lockfiles = %v, want [//requirements:all.txt]", lockfiles)
    }

    scaRules := targetRule.AttrStrings("sca_rules")
    if len(scaRules) != 1 || scaRules[0] != "//semgrep_rules:sca_rules" {
        t.Errorf("sca_rules = %v, want [//semgrep_rules:sca_rules]", scaRules)
    }
}

func TestGenerateRules_SCADisabled(t *testing.T) {
    c := &config.Config{
        Exts: map[string]interface{}{
            semgrepConfigKey: &semgrepConfig{
                enabled:     true,
                scaEnabled:  false,
                lockfiles:   map[string]string{"pip": "//requirements:all.txt"},
                targetKinds: map[string]string{"py_venv_binary": ""},
                languages:   []string{"py"},
            },
        },
    }

    binary := newPyBinaryWithDeps("server", "server.py", []string{"@pip//requests"})
    buildFile := buildFileWithRules(binary)

    args := language.GenerateArgs{
        Config:       c,
        Dir:          "/tmp/test",
        Rel:          "services/myapp",
        RegularFiles: []string{"server.py"},
        File:         buildFile,
    }

    result := generateRules(args)
    targetRule := result.Gen[0]

    // When SCA is disabled, no lockfiles or sca_rules should be set
    lockfiles := targetRule.AttrStrings("lockfiles")
    if len(lockfiles) != 0 {
        t.Errorf("lockfiles should be empty when SCA disabled, got %v", lockfiles)
    }
}
```

**Step 6: Run tests to verify they fail**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //rules_semgrep/gazelle:gazelle_test`
Expected: FAIL (lockfile attrs not set yet)

**Step 7: Create sca.go with dep prefix detection logic**

Create `rules_semgrep/gazelle/sca.go`:

```go
package gazelle

import (
    "strings"

    "github.com/bazelbuild/bazel-gazelle/rule"
)

// depPrefixToEcosystem maps external dep label prefixes to lockfile ecosystems.
var depPrefixToEcosystem = map[string]string{
    "@pip//":     "pip",
    "@npm//":     "pnpm",
    "@go_deps//": "gomod",
}

// detectLockfiles inspects a target's deps for external dependency prefixes
// and returns the matching lockfile labels from the config.
func detectLockfiles(target *rule.Rule, cfg *semgrepConfig) []string {
    if !cfg.scaEnabled || len(cfg.lockfiles) == 0 {
        return nil
    }

    deps := target.AttrStrings("deps")
    ecosystems := make(map[string]bool)

    for _, dep := range deps {
        for prefix, ecosystem := range depPrefixToEcosystem {
            if strings.HasPrefix(dep, prefix) {
                ecosystems[ecosystem] = true
                break
            }
        }
    }

    var lockfiles []string
    for ecosystem := range ecosystems {
        if label, ok := cfg.lockfiles[ecosystem]; ok {
            lockfiles = append(lockfiles, label)
        }
    }

    return lockfiles
}
```

**Step 8: Wire lockfile detection into generateRules**

In `rules_semgrep/gazelle/generate.go`, after setting rules on a `semgrep_target_test` rule, add lockfile detection:

```go
// Detect lockfiles from target deps
if cfg.scaEnabled {
    // For self-targeting kinds, inspect the target itself
    // For indirected kinds, we can't inspect cross-package deps,
    // but still check the rule's own deps
    lockfiles := detectLockfiles(t, cfg)
    if len(lockfiles) > 0 {
        sort.Strings(lockfiles)
        r.SetAttr("lockfiles", lockfiles)
        r.SetAttr("sca_rules", []string{cfg.scaRules})
    }
}
```

Note: `t` here is the original target rule from `findTargets()`. For self-targeting kinds, this is the `py_venv_binary` whose deps we inspect.

**Step 9: Update KnownDirectives and Kinds in language.go**

In `language.go`, add new directives:

```go
func (l *semgrepLang) KnownDirectives() []string {
    return []string{
        "semgrep",
        "semgrep_exclude_rules",
        "semgrep_target_kinds",
        "semgrep_languages",
        "semgrep_sca",
        "semgrep_sca_rules",
        "semgrep_lockfile",
    }
}
```

Update `Kinds()` to include `lockfiles` and `sca_rules` as mergeable attrs:

```go
"semgrep_target_test": {
    MatchAny: false,
    NonEmptyAttrs: map[string]bool{
        "target": true,
        "rules":  true,
    },
    MergeableAttrs: map[string]bool{
        "target":        true,
        "rules":         true,
        "exclude_rules": true,
        "lockfiles":     true,
        "sca_rules":     true,
    },
},
```

**Step 10: Run tests to verify they pass**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //rules_semgrep/gazelle:gazelle_test`
Expected: ALL PASS

**Step 11: Commit**

```bash
git add rules_semgrep/gazelle/config.go rules_semgrep/gazelle/config_test.go rules_semgrep/gazelle/generate.go rules_semgrep/gazelle/generate_test.go rules_semgrep/gazelle/language.go rules_semgrep/gazelle/sca.go
git commit -m "feat(semgrep): add SCA lockfile detection to Gazelle extension"
```

---

### Task 6: Update GitHub Actions Workflow for SCA Rule Vendoring

Extend the update workflow to fetch SCA advisory rules, package them as OCI, and push to GHCR.

**Files:**

- Modify: `.github/workflows/update-semgrep-pro.yaml`

**Step 1: Add SCA rule download step**

After the "Download pro rule packs" step (line 167), add:

```yaml
- name: Download SCA advisory rules
  run: |
    set -euo pipefail
    dir="artifacts/rules-sca"
    mkdir -p "${dir}"

    echo "Downloading SCA supply-chain advisory rules..."
    curl -sSfL \
      "https://semgrep.dev/c/supply-chain" \
      -o "${dir}/supply-chain.yaml"

    echo "Downloaded SCA rules ($(stat --format=%s "${dir}/supply-chain.yaml") bytes)"
```

**Step 2: Add SCA artifact to packaging step**

In the "Package and push OCI artifacts" step, add `rules-sca` to `PRO_ARTIFACTS`:

```yaml
PRO_ARTIFACTS="engine-amd64 engine-arm64 engine-osx-arm64 engine-osx-x86_64 rules-golang rules-python rules-javascript rules-kubernetes rules-sca"
```

**Step 3: Add SCA digest env var to digest update step**

Add to the env block:

```yaml
DIGEST_PRO_RULES_SCA: ${{ steps.digests.outputs.pro_rules_sca }}
```

Add to the digests.bzl template:

```python
    "rules_sca": "${DIGEST_PRO_RULES_SCA}",
```

**Step 4: Commit**

```bash
git add .github/workflows/update-semgrep-pro.yaml
git commit -m "ci(semgrep): add SCA advisory rule vendoring to update workflow"
```

---

### Task 7: Run Gazelle and Verify Generated BUILD Files

Run Gazelle to regenerate BUILD files with the new SCA lockfile attributes.

**Files:**

- Modified by Gazelle: various BUILD files across the repo

**Step 1: Run Gazelle**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel run gazelle`
Expected: BUILD files updated with `lockfiles` and `sca_rules` on `semgrep_target_test` targets that have `@pip//` deps

**Step 2: Review generated changes**

Run: `cd /tmp/claude-worktrees/semgrep-sca && git diff`
Expected: `semgrep_target_test` targets now include `lockfiles` and `sca_rules` attrs where applicable

**Step 3: Run full test suite**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //...`
Expected: ALL PASS (SCA tests SKIP gracefully since rules_sca digest is empty)

**Step 4: Commit**

```bash
git add -A
git commit -m "build(semgrep): regenerate BUILD files with SCA lockfile attrs"
```

---

### Task 8: Update Documentation

Update the README, ADR/docs, and webpage to document SCA support.

**Files:**

- Modify: `rules_semgrep/README.md`
- Modify: `websites/jomcgi.dev/src/pages/engineering.astro`

**Step 1: Update rules_semgrep README**

Add SCA section after "Rules" table (around line 33). Update the rules table to include SCA attributes:

- Add a "Supply Chain Analysis (SCA)" section explaining lockfile scanning
- Update `semgrep_test` and `semgrep_target_test` examples to show `lockfiles` and `sca_rules`
- Add lockfile kind detection table
- Update Common Attributes table with `lockfiles` and `sca_rules`
- Update Gazelle directives table with `semgrep_sca`, `semgrep_sca_rules`, `semgrep_lockfile`
- Add `sca_rules` to Rule Files table
- Update the "How It Works" mermaid diagram to show lockfile → SCA flow

**Step 2: Update engineering webpage**

In `websites/jomcgi.dev/src/pages/engineering.astro`:

- Update the `semgrepDiagram` mermaid flowchart to include SCA/lockfile flow
- Update the `rules_semgrep` description to mention SCA reachability analysis

**Step 3: Commit**

```bash
git add rules_semgrep/README.md websites/jomcgi.dev/src/pages/engineering.astro
git commit -m "docs(semgrep): document SCA lockfile scanning support"
```

---

### Task 9: Format, Test, Push, and Create PR

Final verification and PR creation.

**Step 1: Format all code**

Run: `cd /tmp/claude-worktrees/semgrep-sca && format`

**Step 2: Run full test suite**

Run: `cd /tmp/claude-worktrees/semgrep-sca && bazel test //...`
Expected: ALL PASS

**Step 3: Commit any format changes**

```bash
git add -A
git diff --cached --quiet || git commit -m "style: format code"
```

**Step 4: Push and create PR**

```bash
git push -u origin feat/semgrep-sca
gh pr create --title "feat(semgrep): add SCA lockfile scanning with reachability" --body "$(cat <<'EOF'
## Summary

- Extends `semgrep_target_test` and `semgrep_test` with optional `lockfiles` and `sca_rules` attributes
- Single test invocation runs SAST + SCA simultaneously via semgrep-core's `products: ["sast", "sca"]`
- Reachability analysis: links lockfile dependencies to source targets via aspect, distinguishing reachable vs unreachable vulnerabilities
- SCA advisory rules vendored as OCI artifact on GHCR (same pattern as Pro rule packs)
- Gazelle auto-detects lockfiles by inspecting target deps for `@pip//`, `@npm//`, Go module prefixes
- Graceful degradation: empty SCA digest → SKIP (no failure)
- Updated docs, README, and engineering webpage

## Design doc

`docs/plans/2026-03-04-semgrep-sca-design.md`

## Lockfile support

| Ecosystem | Lockfile | Detection |
|---|---|---|
| Go | go.sum | `@go_deps//` dep prefix |
| Python | requirements.txt | `@pip//` dep prefix |
| JS | pnpm-lock.yaml | `@npm//` dep prefix |

## Test plan

- [ ] Gazelle unit tests pass for SCA config and lockfile detection
- [ ] Existing SAST tests unaffected (no lockfiles → pure SAST)
- [ ] SCA tests gracefully SKIP when rules_sca digest is empty
- [ ] `bazel test //...` passes
- [ ] Generated BUILD files include lockfiles attrs where targets have external deps
- [ ] Update workflow includes SCA rule vendoring step

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

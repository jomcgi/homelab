# Semgrep Bazel Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run custom semgrep rules as hermetic, cacheable Bazel tests against both source code and rendered Helm manifests.

**Architecture:** Semgrep is acquired via pip (`py_console_script_binary`). A `semgrep_test` macro wraps `sh_test` for source files. A `semgrep_manifest_test` macro combines Helm rendering + semgrep scanning for manifests. The `argocd_app` macro automatically creates a `semgrep_test` for every overlay.

**Tech Stack:** Bazel (bzlmod), aspect_rules_py (pip), rules_shell (sh_test), Semgrep CLI, Helm CLI

**Design doc:** `docs/plans/2026-03-02-semgrep-bazel-design.md`

---

### Task 1: Add semgrep pip dependency

**Files:**

- Modify: `requirements/tools.in`
- Regenerate: `requirements/all.txt`

**Step 1: Add semgrep to tools.in**

Add `semgrep` to `requirements/tools.in`:

```
# Tools that are run manually for developmer tasks or run by Bazel
# but not used by tests or at runtime.
copier>=9.11.2
semgrep
```

**Step 2: Regenerate the lock file**

Run: `bazel run //requirements:requirements.all`

This resolves semgrep + all transitive deps and writes pinned hashes to `all.txt`.
The `universal = True` flag ensures both macOS and Linux wheels are included.

**Step 3: Verify the dependency resolves**

Run: `grep semgrep requirements/all.txt | head -5`
Expected: Lines showing `semgrep==X.Y.Z` with `--hash=sha256:...`

**Step 4: Commit**

```bash
git add requirements/tools.in requirements/all.txt
git commit -m "build: add semgrep pip dependency for Bazel integration"
```

---

### Task 2: Create semgrep binary target

**Files:**

- Create: `tools/semgrep/BUILD`

**Step 1: Create the BUILD file**

```starlark
load("@rules_python//python/entry_points:py_console_script_binary.bzl", "py_console_script_binary")

py_console_script_binary(
    name = "semgrep",
    pkg = "@pip//semgrep",
    visibility = ["//visibility:public"],
)
```

This follows the existing `copier` pattern in `tools/BUILD`.

**Step 2: Build the binary to verify**

Run: `bazel build //tools/semgrep`
Expected: Build succeeds. The binary wraps semgrep's entry point with Bazel's hermetic Python.

**Step 3: Smoke test the binary**

Run: `bazel run //tools/semgrep -- --version`
Expected: Prints semgrep version (e.g., `1.153.0`)

**Step 4: Commit**

```bash
git add tools/semgrep/BUILD
git commit -m "build: add hermetic semgrep binary via py_console_script_binary"
```

---

### Task 3: Import and organize semgrep rules

Import the existing rules from the `feat/semgrep-rules` branch and add BUILD
filegroups so Bazel targets can depend on rule sets by category.

**Files:**

- Copy from `feat/semgrep-rules`: `semgrep_rules/` directory (all `.yaml` and fixture files)
- Create: `semgrep_rules/BUILD`

**Step 1: Copy rules from the existing branch**

```bash
git checkout feat/semgrep-rules -- semgrep_rules/
```

This brings in:

- `semgrep_rules/bazel/no-rules-python.yaml` + `.build` fixture
- `semgrep_rules/shell/no-direct-test.yaml` + `.bash` fixture
- `semgrep_rules/shell/no-kubectl-mutate.yaml` + `.bash` fixture
- `semgrep_rules/dockerfile/no-dockerfile.yaml` + `.dockerfile` fixture

**Step 2: Create the BUILD file with filegroups**

Create `semgrep_rules/BUILD`:

```starlark
package(default_visibility = ["//visibility:public"])

filegroup(
    name = "shell_rules",
    srcs = glob(["shell/*.yaml"]),
)

filegroup(
    name = "bazel_rules",
    srcs = glob(["bazel/*.yaml"]),
)

filegroup(
    name = "dockerfile_rules",
    srcs = glob(["dockerfile/*.yaml"]),
)

filegroup(
    name = "kubernetes_rules",
    srcs = glob(["kubernetes/*.yaml"]),
)

filegroup(
    name = "all_rules",
    srcs = glob(["**/*.yaml"]),
)
```

**Step 3: Build to verify filegroups resolve**

Run: `bazel build //semgrep_rules:shell_rules //semgrep_rules:bazel_rules`
Expected: Build succeeds (filegroups find the YAML files).

**Step 4: Commit**

```bash
git add semgrep_rules/
git commit -m "build: import semgrep rules and add Bazel filegroups"
```

---

### Task 4: Create `rules_semgrep` package with `semgrep_test` macro

**Files:**

- Create: `rules_semgrep/BUILD`
- Create: `rules_semgrep/semgrep-test.sh`
- Create: `rules_semgrep/test.bzl`
- Create: `rules_semgrep/defs.bzl`

**Step 1: Create the test runner script**

Create `rules_semgrep/semgrep-test.sh`:

```bash
#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep against source files with given rules
#
# Usage: semgrep-test.sh <semgrep-binary> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.

set -euo pipefail

if [[ $# -lt 3 ]]; then
	echo "Usage: $0 <semgrep-binary> <rule-files...> -- <source-files...>"
	exit 1
fi

SEMGREP="$1"
shift

# Collect rule files until we hit the -- separator
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	RULES+=("--config" "$1")
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and source files"
	exit 1
fi
shift # skip --

echo "Running semgrep scan:"
echo "  Rules: ${RULES[*]}"
echo "  Files: $*"
echo ""

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$@"; then
	echo "PASSED: No semgrep findings"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations"
	exit 1
fi
```

**Step 2: Create the Starlark macro**

Create `rules_semgrep/test.bzl`:

```starlark
"""Bazel test rules for running semgrep scans."""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

def semgrep_test(name, srcs, rules, **kwargs):
    """Creates a cacheable test that runs semgrep against source files.

    Runs semgrep with the given rule configs against the source files and
    fails if any violations are found. Results are cached by Bazel based
    on input file hashes — only re-runs when sources or rules change.

    Args:
        name: Name of the test target
        srcs: Source files to scan (labels)
        rules: Semgrep rule config files or filegroups (labels)
        **kwargs: Additional arguments passed to sh_test
    """
    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = [
            "$(rootpath //tools/semgrep)",
        ] + ["$(rootpath {})".format(r) for r in rules] +
            ["--"] +
            ["$(rootpath {})".format(s) for s in srcs],
        data = [
            "//tools/semgrep",
        ] + rules + srcs,
        **kwargs
    )
```

**Step 3: Create the public API**

Create `rules_semgrep/defs.bzl`:

```starlark
"""Public API for rules_semgrep — Bazel rules for running semgrep scans."""

load("//rules_semgrep:test.bzl", _semgrep_test = "semgrep_test")

semgrep_test = _semgrep_test
```

**Step 4: Create the BUILD file**

Create `rules_semgrep/BUILD`:

```starlark
load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

exports_files([
    "semgrep-test.sh",
])

bzl_library(
    name = "defs",
    srcs = [
        "defs.bzl",
        "test.bzl",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "@rules_shell//shell:rules_bzl",  # keep
    ],
)
```

**Step 5: Write a smoke test to verify the rule works**

Create a temporary test target. Add to `scripts/BUILD` (which has shell scripts):

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_test")

semgrep_test(
    name = "semgrep_shell_test",
    srcs = [":signoz-mcp-wrapper.sh"],
    rules = ["//semgrep_rules:shell_rules"],
)
```

Run: `bazel test //scripts:semgrep_shell_test`
Expected: PASS (signoz-mcp-wrapper.sh shouldn't violate shell rules)

**Step 6: Remove the smoke test from scripts/BUILD** (it was just for validation)

**Step 7: Commit**

```bash
git add rules_semgrep/
git commit -m "feat: add semgrep_test Bazel rule for source code scanning"
```

---

### Task 5: Write Kubernetes manifest semgrep rules

**Files:**

- Create: `semgrep_rules/kubernetes/no-host-network.yaml`
- Create: `semgrep_rules/kubernetes/no-privileged.yaml`

These are starter rules. The `no-run-as-root` and `require-resource-limits`
checks are NOT included because this repo's charts intentionally use
`runAsNonRoot: true` and set resource limits — but not all charts may set them
in default values (some rely on overlay overrides). Start with rules that have
zero false positives, add more rules incrementally.

**Step 1: Create no-host-network rule**

Create `semgrep_rules/kubernetes/no-host-network.yaml`:

```yaml
rules:
  - id: no-host-network
    languages: [yaml]
    severity: ERROR
    message: >-
      Pod uses host network namespace. This gives the pod access to the
      loopback device and could be used to snoop on network activity of
      other pods on the same node. Remove 'hostNetwork: true'.
    metadata:
      category: security
    patterns:
      - pattern-inside: |
          spec:
            ...
      - pattern: |
          hostNetwork: true
```

**Step 2: Create no-privileged rule**

Create `semgrep_rules/kubernetes/no-privileged.yaml`:

```yaml
rules:
  - id: no-privileged
    languages: [yaml]
    severity: ERROR
    message: >-
      Container is running in privileged mode. This grants the container
      root-equivalent capabilities on the host. Remove 'privileged: true'
      from securityContext.
    metadata:
      category: security
    patterns:
      - pattern-inside: |
          containers:
            ...
      - pattern: |
          securityContext:
            ...
            privileged: true
```

**Step 3: Verify rules parse correctly**

Run: `bazel run //tools/semgrep -- --config semgrep_rules/kubernetes/ --validate`
Expected: Rules validate without errors.

**Step 4: Commit**

```bash
git add semgrep_rules/kubernetes/
git commit -m "feat: add Kubernetes manifest semgrep rules"
```

---

### Task 6: Create `semgrep_manifest_test` for rendered manifests

This macro combines Helm rendering + semgrep scanning in a single test.
It follows the same `sh_test` wrapping pattern as `helm_template_test`.

**Files:**

- Create: `rules_semgrep/semgrep-manifest-test.sh`
- Modify: `rules_semgrep/test.bzl` (add `semgrep_manifest_test`)
- Modify: `rules_semgrep/defs.bzl` (export new macro)
- Modify: `rules_semgrep/BUILD` (export new script)

**Step 1: Create the manifest test runner script**

Create `rules_semgrep/semgrep-manifest-test.sh`:

```bash
#!/usr/bin/env bash
# semgrep-manifest-test.sh - Renders Helm manifests and scans with semgrep
#
# Usage: semgrep-manifest-test.sh <semgrep> <helm> <release> <chart> <namespace> <rules...> -- <values-files...>
#
# Combines helm template rendering with semgrep scanning in a single test.
# Exit code 0 = no findings, non-zero = violations found or render failure.

set -euo pipefail

if [[ $# -lt 6 ]]; then
	echo "Usage: $0 <semgrep> <helm> <release> <chart> <namespace> <rules...> -- <values...>"
	exit 1
fi

SEMGREP="$1"
HELM="$2"
RELEASE="$3"
CHART="$4"
NAMESPACE="$5"
shift 5

# Collect rule files until -- separator
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	RULES+=("--config" "$1")
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and values files"
	exit 1
fi
shift # skip --

# Build values arguments
VALUES_ARGS=()
for vf in "$@"; do
	VALUES_ARGS+=("--values" "$vf")
done

# Render manifests to a temp file with .yaml extension (semgrep needs it)
MANIFESTS="${TEST_TMPDIR}/rendered-manifests.yaml"

echo "Rendering manifests:"
echo "  Release:   $RELEASE"
echo "  Chart:     $CHART"
echo "  Namespace: $NAMESPACE"
echo "  Values:    $*"

if ! "$HELM" template "$RELEASE" "$CHART" \
	--namespace "$NAMESPACE" \
	"${VALUES_ARGS[@]}" > "$MANIFESTS"; then
	echo "FAILED: Helm template rendering failed"
	exit 1
fi

echo ""
echo "Scanning rendered manifests with semgrep:"
echo "  Rules: ${RULES[*]}"
echo ""

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$MANIFESTS"; then
	echo "PASSED: No semgrep findings in rendered manifests"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations in rendered manifests"
	exit 1
fi
```

**Step 2: Add `semgrep_manifest_test` macro to test.bzl**

Append to `rules_semgrep/test.bzl`:

```starlark
def semgrep_manifest_test(
        name,
        chart,
        chart_files,
        release_name,
        namespace,
        values_files,
        rules = ["//semgrep_rules:kubernetes_rules"],
        **kwargs):
    """Creates a test that renders Helm manifests and scans them with semgrep.

    Combines helm template rendering with semgrep scanning. Fails if either
    rendering fails or semgrep finds violations. Results are cached by Bazel.

    Args:
        name: Name of the test target
        chart: Path to chart directory (e.g., "charts/todo")
        chart_files: Label for chart's filegroup (e.g., "//charts/todo:chart")
        release_name: Helm release name
        namespace: Kubernetes namespace for rendering
        values_files: List of values file labels in order
        rules: Semgrep rule config files (default: kubernetes rules)
        **kwargs: Additional arguments passed to sh_test
    """
    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-manifest-test.sh"],
        args = [
            "$(rootpath //tools/semgrep)",
            "$(rootpath @multitool//tools/helm)",
            release_name,
            chart,
            namespace,
        ] + ["$(rootpath {})".format(r) for r in rules] +
            ["--"] +
            ["$(rootpath {})".format(vf) for vf in values_files],
        data = [
            "//tools/semgrep",
            "@multitool//tools/helm",
            chart_files,
        ] + rules + values_files,
        **kwargs
    )
```

**Step 3: Update defs.bzl to export the new macro**

Update `rules_semgrep/defs.bzl`:

```starlark
"""Public API for rules_semgrep — Bazel rules for running semgrep scans."""

load("//rules_semgrep:test.bzl", _semgrep_manifest_test = "semgrep_manifest_test", _semgrep_test = "semgrep_test")

semgrep_test = _semgrep_test
semgrep_manifest_test = _semgrep_manifest_test
```

**Step 4: Update BUILD to export the new script**

Update `rules_semgrep/BUILD` exports_files:

```starlark
exports_files([
    "semgrep-test.sh",
    "semgrep-manifest-test.sh",
])
```

**Step 5: Smoke test against a single overlay**

Manually add a test target to `overlays/prod/todo/BUILD` (temporarily):

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_manifest_test")

semgrep_manifest_test(
    name = "semgrep_test",
    chart = "charts/todo",
    chart_files = "//charts/todo:chart",
    namespace = "todo",
    release_name = "todo",
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
    ],
)
```

Run: `bazel test //overlays/prod/todo:semgrep_test`
Expected: PASS (todo chart shouldn't use hostNetwork or privileged mode)

**Step 6: Remove the manual smoke test** (argocd_app will auto-generate it next)

**Step 7: Commit**

```bash
git add rules_semgrep/
git commit -m "feat: add semgrep_manifest_test for rendered Helm manifests"
```

---

### Task 7: Wire semgrep into `argocd_app` macro

**Files:**

- Modify: `rules_helm/app.bzl`

**Step 1: Add semgrep_manifest_test import and parameter**

Modify `rules_helm/app.bzl` — add the import at the top:

```starlark
load("//rules_semgrep:test.bzl", "semgrep_manifest_test")
```

Add `generate_semgrep` and `semgrep_rules` parameters to the `argocd_app` function
signature (after `generate_diff`):

```python
        generate_semgrep = True,
        semgrep_rules = ["//semgrep_rules:kubernetes_rules"],
```

Update the docstring Args section to include:

```
        generate_semgrep: If True, create semgrep_test for rendered manifests (default: True)
        semgrep_rules: List of semgrep rule config labels for manifest scanning
```

**Step 2: Add the semgrep_test target creation**

Add after the `generate_diff` block (before the final closing of the function):

```starlark
    if generate_semgrep:
        semgrep_manifest_test(
            name = "semgrep_test",
            chart = chart,
            chart_files = chart_files,
            release_name = release_name,
            namespace = namespace,
            values_files = values_files,
            rules = semgrep_rules,
            tags = tags + ["semgrep"],
        )
```

**Step 3: Update the rules_helm BUILD bzl_library deps**

Add to `rules_helm/BUILD` bzl_library deps:

```starlark
        "//rules_semgrep:defs",  # keep
```

**Step 4: Regenerate BUILD files to pick up new targets**

Run: `bazel run gazelle`

This will regenerate all overlay BUILD files. Since Gazelle generates
`argocd_app()` calls and the macro now includes `semgrep_test`, every overlay
automatically gets a semgrep test target.

**Step 5: Verify all overlay semgrep tests pass**

Run: `bazel test //overlays/... --test_tag_filters=semgrep`
Expected: All PASS. If any fail, the chart has a real issue to fix.

**Step 6: Commit**

```bash
git add rules_helm/app.bzl rules_helm/BUILD
git commit -m "feat: wire semgrep scanning into argocd_app macro"
```

---

### Task 8: Add source code semgrep tests

Add `semgrep_test` targets to BUILD files that have relevant shell script or
Starlark targets. Start with `scripts/BUILD` (shell scripts) and
`tools/lint/BUILD` (bzl files).

**Files:**

- Modify: `scripts/BUILD`

**Step 1: Add semgrep test for shell scripts in scripts/**

Append to `scripts/BUILD`:

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_test")

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.sh"]),
    rules = ["//semgrep_rules:shell_rules"],
)
```

**Step 2: Run the test**

Run: `bazel test //scripts:semgrep_test`
Expected: PASS (none of the scripts should be running `go test` directly or
using mutating kubectl commands)

**Step 3: Commit**

```bash
git add scripts/BUILD
git commit -m "feat: add semgrep source code tests for shell scripts"
```

---

### Task 9: End-to-end verification

**Step 1: Run all tests**

Run: `bazel test //...`
Expected: All tests pass, including new semgrep tests.

**Step 2: Verify semgrep tests are discoverable**

Run: `bazel query 'tests(//...)' | grep semgrep`
Expected: Shows semgrep_test targets for each overlay and for scripts.

**Step 3: Verify caching works**

Run: `bazel test //overlays/prod/todo:semgrep_test` (second time)
Expected: `(cached) PASSED` — Bazel doesn't re-run since nothing changed.

**Step 4: Verify a violation is caught**

Create a temporary test file with a known violation and run semgrep against it
to confirm the rules catch it. Then remove the file.

**Step 5: Push and create PR**

```bash
git push -u origin feat/semgrep-bazel
gh pr create --title "feat: add semgrep Bazel integration" --body "..."
```

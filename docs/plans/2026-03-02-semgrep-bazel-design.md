# Semgrep Bazel Integration Design

## Problem

Semgrep rules exist in `semgrep_rules/` and run via pre-commit, but they're not
enforced in CI (BuildBuddy). We want Bazel to be the authoritative enforcement
for semgrep rules — running them hermetically against both source code and
rendered Helm manifests as cacheable `bazel test` targets.

## Constraints

- **No external rules** — only custom rules in `semgrep_rules/`; deterministic
- **Hermetic** — semgrep binary managed by Bazel, not system-installed
- **Rendered outputs** — scan Helm template output YAML, not just source
- **Automatic** — runs as part of `bazel test //...`

## Design

### 1. Semgrep Binary via pip

Semgrep doesn't publish standalone binaries — it's distributed as a Python
package with `semgrep-core` (OCaml native binary) bundled in the wheel.

- Add `semgrep` to `requirements/tools.in`
- Regenerate `requirements/all.txt`
- Create `py_console_script_binary(name = "semgrep", pkg = "@pip//semgrep")`
  in `tools/semgrep/BUILD`

This follows the existing `copier` pattern in `tools/BUILD` and gives us a
hermetic `//tools/semgrep` label.

### 2. `semgrep_test` Rule

New `rules_semgrep/` package (following `rules_helm/` pattern):

```
rules_semgrep/
├── BUILD            # bzl_library
├── defs.bzl         # Public API: exports semgrep_test
├── test.bzl         # semgrep_test macro (wraps sh_test)
└── semgrep-test.sh  # Test runner script
```

`semgrep_test` macro interface:

```starlark
semgrep_test(
    name = "semgrep_test",
    srcs = [":my_script.sh"],           # files to scan
    rules = ["//semgrep_rules:shell_rules"],  # semgrep rule configs
)
```

Implementation: `sh_test` that runs
`semgrep --config <rules> --error --no-git-ignore <srcs>`.
Fully cacheable — only re-runs when source files or rules change.

### 3. Manifest Scanning via `argocd_app`

The `argocd_app` macro gains an optional `semgrep_test` target:

1. Uses existing `helm_render` to produce rendered manifests (already cached)
2. Passes rendered YAML to `semgrep_test` with `//semgrep_rules:kubernetes_rules`
3. Every overlay automatically gets a `semgrep_test` alongside `template_test`

Data flow: `chart + values → helm_render → rendered YAML → semgrep_test`

Controlled by a `generate_semgrep` parameter (default `True`).

### 4. Semgrep Rules Organization

```
semgrep_rules/
├── BUILD                        # filegroup targets per category
├── bazel/
│   ├── no-rules-python.yaml     # existing
│   └── no-rules-python.build    # test fixture
├── shell/
│   ├── no-direct-test.yaml      # existing
│   ├── no-direct-test.bash      # test fixture
│   ├── no-kubectl-mutate.yaml   # existing
│   └── no-kubectl-mutate.bash   # test fixture
├── dockerfile/
│   ├── no-dockerfile.yaml       # existing
│   └── no-dockerfile.dockerfile # test fixture
└── kubernetes/                  # NEW — manifest rules
    ├── no-run-as-root.yaml
    ├── no-host-network.yaml
    ├── require-resource-limits.yaml
    └── *.yaml                   # test fixtures
```

BUILD filegroups:

- `//semgrep_rules:shell_rules`
- `//semgrep_rules:bazel_rules`
- `//semgrep_rules:kubernetes_rules`
- `//semgrep_rules:all_rules` (union for pre-commit)

### 5. Source Code Integration

`semgrep_test` targets added manually to BUILD files where relevant targets
exist. Gazelle extension is out of scope for v1.

Example usage:

```starlark
load("//rules_semgrep:defs.bzl", "semgrep_test")

semgrep_test(
    name = "semgrep_test",
    srcs = [":deploy.sh"],
    rules = ["//semgrep_rules:shell_rules"],
)
```

### 6. Pre-commit Stays

Pre-commit remains for fast local feedback. Bazel is the authoritative CI
enforcement. Both use the same rule YAML files from `semgrep_rules/`.

## Out of Scope

- Gazelle extension for auto-generating `semgrep_test` targets
- `aspect_rules_lint` integration (revisit if semgrep gets official support)
- External/community semgrep rules (only custom rules for determinism)

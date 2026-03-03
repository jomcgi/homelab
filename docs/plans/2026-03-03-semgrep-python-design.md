# Semgrep Python Rules + Gazelle Auto-Generation

## Context

PR #692 added hermetic semgrep scanning as Bazel tests for Kubernetes manifests, shell scripts, and Starlark files. The `semgrep_test` macro and shell runner are language-agnostic — semgrep natively supports Python via AST parsing.

This design extends coverage to Python with two additions:
1. Python-specific semgrep rules (security + repo conventions)
2. A Gazelle extension that auto-generates `semgrep_test` targets for Python packages

## Goals

- Catch security anti-patterns and repo convention violations in Python code
- Zero developer friction — `format` auto-generates targets, `bazel test` is the feedback loop
- Per-package opt-out via Gazelle directives for legitimate exceptions

## Non-Goals

- Auto-generating semgrep_test for shell/Starlark (existing manual targets from PR #692 are sufficient)
- Vendoring Semgrep Pro rules (future work, flat structure accommodates this)
- Gazelle extension for other languages (can extend later)

## Rules

Five rules in `semgrep_rules/python/`, combining security guardrails and repo conventions:

### Security

| Rule | Pattern | Severity | Rationale |
|------|---------|----------|-----------|
| `no-shell-true` | `subprocess.*(..., shell=True, ...)` | ERROR | Command injection risk |
| `no-os-system` | `os.system(...)` | ERROR | Command injection; use subprocess.run() |
| `no-eval-exec` | `eval(...)` / `exec(...)` | ERROR | Arbitrary code execution |

### Conventions

| Rule | Pattern | Severity | Rationale |
|------|---------|----------|-----------|
| `no-requests` | `import requests` | WARNING | Prefer httpx for async consistency |
| `no-hardcoded-secret` | `password = "..."` / `api_key = "..."` / `secret = "..."` | ERROR | Use env vars or pydantic-settings |

Each rule YAML includes a companion `.py` test fixture containing code that triggers the rule, verifiable via `bazel test //semgrep_rules:python_rules_test`.

## Gazelle Extension

### Architecture

A new `rules_semgrep/gazelle/` Go package implementing the `language.Language` interface (same pattern as `rules_helm/gazelle/`).

**Detection:** Scans `args.RegularFiles` for `*.py` files. If any exist, emits:

```starlark
semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
```

**Directives:**

- `# gazelle:semgrep_exclude_rules no-requests,no-hardcoded-secret` — sets `exclude_rules` attribute
- `# gazelle:semgrep disabled` — skips generation entirely

### Integration

Added to the custom `gazelle_binary` in the root BUILD file alongside existing extensions.

Since `bazel run gazelle` runs inside `format`, every `format` invocation ensures Python packages have semgrep scanning.

## File Changes

### New Files

```
rules_semgrep/gazelle/
├── BUILD
├── language.go          # Language interface implementation
├── config.go            # Directive parsing
├── generate.go          # *.py detection → semgrep_test generation
├── generate_test.go     # Table-driven generation tests
├── language_test.go     # Directive/config tests

semgrep_rules/python/
├── no-shell-true.yaml
├── no-shell-true.py     # Test fixture
├── no-os-system.yaml
├── no-os-system.py
├── no-eval-exec.yaml
├── no-eval-exec.py
├── no-requests.yaml
├── no-requests.py
├── no-hardcoded-secret.yaml
├── no-hardcoded-secret.py
```

### Modified Files

- `semgrep_rules/BUILD` — add `python_rules` filegroup
- `BUILD` (root) — add `//rules_semgrep/gazelle` to gazelle_binary languages + ENABLE_LANGUAGES
- Service BUILD files — gazelle auto-adds `semgrep_test` on next run

### Unchanged

- `rules_semgrep/test.bzl` — macro already handles any language
- `rules_semgrep/semgrep-test.sh` — runner is language-agnostic
- Existing shell/Bazel/k8s semgrep targets

## Testing

1. Each rule YAML has a `.py` fixture — scanned by `bazel test //semgrep_rules:python_rules_test`
2. Gazelle extension has Go unit tests (table-driven: file presence → rule generation)
3. Running `format` then `bazel test //...` validates end-to-end

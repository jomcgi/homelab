# Semgrep SCA (Supply Chain Analysis) for rules_semgrep

**Date:** 2026-03-04
**Status:** Proposed

## Problem

The `rules_semgrep` Bazel ruleset currently supports SAST (static analysis) scanning of source code and Helm manifests. It does not support SCA (Software Composition Analysis) — scanning lockfile dependencies against CVE advisory databases.

SCA catches a different class of vulnerabilities: known CVEs in third-party packages your code depends on. With reachability analysis (Pro engine), it can further distinguish between dependencies that are merely present vs. ones where vulnerable code paths are actually invoked.

## Design

### Approach: Extend Existing Rules

Rather than creating new rule types, extend `semgrep_target_test` and `semgrep_test` with optional SCA attributes. This allows a single test invocation to run SAST + SCA simultaneously, since semgrep-core's `products` field supports `["sast", "sca"]` in one pass.

### Rule Changes

#### `semgrep_target_test` (target_test.bzl)

New optional attributes:

- `lockfiles` (label list, default `[]`) — lockfile(s) to scan for vulnerable dependencies
- `sca_rules` (label list, default `[]`) — SCA advisory rule files (separate from SAST `rules`)

When `lockfiles` is non-empty:
- The test script adds `"sca"` to the products list in `targets.json`
- Each `CodeTarget` gets a `dependency_source` field linking to the lockfile
- Pro engine performs reachability analysis across source + lockfile

When `lockfiles` is empty, behavior is identical to today (pure SAST).

```starlark
semgrep_target_test(
    name = "auth_semgrep",
    target = ":auth",
    rules = ["//semgrep_rules:python_rules"],
    lockfiles = ["//requirements:all.txt"],
    sca_rules = ["//semgrep_rules:sca_rules"],
)
```

#### `semgrep_test` (test.bzl)

Same new optional attributes. When `lockfiles` is provided without `srcs`, generates `DependencySourceTarget` entries for lockfile-only scanning (no reachability).

### targets.json Format

semgrep-core's ATD schema defines two target types relevant to SCA:

**With reachability (source target + lockfile):**

```json
["Targets", [
  ["CodeTarget", {
    "path": {"fpath": "/path/to/main.py", "ppath": "/path/to/main.py"},
    "analyzer": "python",
    "products": ["sast", "sca"],
    "dependency_source": ["LockfileOnly", {
      "kind": "PipRequirementsTxt",
      "path": "/path/to/requirements.txt"
    }]
  }]
]]
```

**Lockfile-only (no source target):**

```json
["Targets", [
  ["DependencySourceTarget", ["LockfileOnly", {
    "kind": "GoModLock",
    "path": "/path/to/go.sum"
  }]]
]]
```

### Lockfile Kind Detection

The test script auto-detects `lockfile_kind` from filename:

| Filename Pattern | lockfile_kind | Ecosystem |
|---|---|---|
| `go.sum` | `GoModLock` | Go |
| `requirements*.txt`, `requirements*.pip` | `PipRequirementsTxt` | Python |
| `poetry.lock` | `PoetryLock` | Python |
| `Pipfile.lock` | `PipfileLock` | Python |
| `uv.lock` | `UvLock` | Python |
| `package-lock.json` | `NpmPackageLockJson` | JS |
| `yarn.lock` | `YarnLock` | JS |
| `pnpm-lock.yaml` | `PnpmLock` | JS |

**Not supported:** apko lockfiles (Semgrep doesn't natively support them).

### Test Script Changes

`semgrep-test.sh` extended argument format:

```
semgrep-test.sh <rule-files...> -- <source-files...> [-- <lockfile-files...>]
```

The third section (after second `--`) contains lockfiles. When present:
1. Lockfiles are copied to the scan directory alongside sources
2. `detect_lockfile_kind()` maps filename to ATD enum
3. `products` becomes `["sast", "sca"]` for `CodeTarget` entries
4. Each `CodeTarget` gets `dependency_source` pointing to the lockfile
5. SCA rules are merged with SAST rules for the invocation

When no lockfiles are provided, the script is fully backwards-compatible.

### SCA Rule Vendoring

SCA advisory rules (CVE database) are vendored as an OCI artifact on GHCR, following the existing Pro rule pack pattern.

**Layered approach:**
1. **Public registry** — baseline CVE advisory rules from `https://semgrep.dev/c/supply-chain` (unauthenticated)
2. **Authenticated overlay** — deployment-specific rules from `/api/cli/scans` when `SEMGREP_APP_TOKEN` is available

**New OCI artifact:** `ghcr.io/jomcgi/homelab/semgrep-sca-rules`

**Fetching:** Uses existing `oci_archive.bzl` repository rule with digest pinning.

**In `third_party/semgrep_pro/extensions.bzl`:**

```starlark
oci_archive(
    name = "semgrep_sca_rules",
    image = "ghcr.io/jomcgi/homelab/semgrep-sca-rules",
    digest = SEMGREP_PRO_DIGESTS["rules_sca"],
    strip_prefix = "rules",
    build_file_content = _RULES_BUILD_FILE_CONTENT,
)
```

**In `semgrep_rules/BUILD`:**

```starlark
filegroup(
    name = "sca_rules",
    srcs = ["@semgrep_sca_rules//:rules"],
    visibility = ["//visibility:public"],
)
```

**Update workflow:** Extend `.github/workflows/update-semgrep-pro.yaml` to fetch SCA rules from the registry, package as OCI, push to GHCR, and update the digest.

### Gazelle Auto-Generation

The Gazelle extension is extended to auto-discover lockfiles and wire them into generated targets.

**Dep prefix detection:** When generating `semgrep_target_test`, the extension inspects the target's `deps` for known external dependency prefixes:

| Dep Prefix | Lockfile | Ecosystem |
|---|---|---|
| `@pip//` | `//requirements:all.txt` | Python |
| `@npm//` or pnpm deps | `//:pnpm-lock.yaml` | JS |
| Go module deps | `//:go.sum` | Go |

**Algorithm:**
1. For each target matching `semgrep_target_kinds`, read its `deps` list from the BUILD AST
2. Match dep labels against known prefixes
3. Map matched prefixes to lockfile labels (hardcoded defaults, overridable via directive)
4. Add `lockfiles` and `sca_rules` attributes to the generated `semgrep_target_test`

**New directives:**

```starlark
# gazelle:semgrep_sca disabled                        # Disable SCA generation
# gazelle:semgrep_sca_rules //custom:rules             # Override SCA rule target
# gazelle:semgrep_lockfile pip //requirements:all.txt   # Override lockfile for pip deps
# gazelle:semgrep_lockfile pnpm //:pnpm-lock.yaml      # Override lockfile for pnpm deps
# gazelle:semgrep_lockfile gomod //:go.sum              # Override lockfile for Go deps
```

**Default lockfile paths (configurable via directives):**

```go
var defaultLockfiles = map[string]string{
    "pip":   "//requirements:all.txt",
    "pnpm":  "//:pnpm-lock.yaml",
    "gomod": "//:go.sum",
}
```

### Graceful Degradation

Consistent with existing patterns:
- **No Pro engine** → SCA test SKIP (SCA requires Pro)
- **No GHCR token** → SCA rules empty → SCA test SKIP
- **Empty SCA digest** → empty filegroup → no SCA rules → SKIP
- **No lockfiles detected** → no `lockfiles` attribute generated → pure SAST (unchanged)

## Scope

**In scope:**
- Extend `semgrep_target_test` and `semgrep_test` with lockfile/SCA attributes
- Modify `semgrep-test.sh` to generate SCA-aware `targets.json`
- Add SCA rule vendoring via OCI artifact
- Extend Gazelle to auto-detect lockfiles via dep prefix detection
- Support Go, Python, JS lockfile ecosystems

**Out of scope:**
- apko lockfile support (not natively supported by Semgrep)
- Secrets scanning (future work, same `products` mechanism)
- Custom SCA policies (future: authenticated API overlay)

## References

- [Semgrep Supply Chain overview](https://semgrep.dev/docs/semgrep-supply-chain/overview)
- [Supported lockfile formats](https://semgrep.dev/docs/semgrep-supply-chain/sca-package-manager-support)
- [semgrep-interfaces ATD schema](https://github.com/semgrep/semgrep-interfaces/blob/main/semgrep_output_v1.atd)
- [Reachability analysis](https://semgrep.dev/blog/2024/sca-reachability-analysis-methods/)

# Semgrep Aspect Aggregation Design

## Problem

The `rules_semgrep` Gazelle extension generates one `semgrep_test` per Python file.
This has two issues:

1. **`--pro` cross-file analysis is wasted** — each test only sees one file, so there
   is no cross-file context for semgrep to analyze.
2. **Test count scales with file count** — `knowledge_graph/app/` has 11 per-file tests
   where 3 binary-level tests would cover the same code with meaningful cross-file context.

## Goal

Aggregate semgrep tests under binary targets using a Bazel aspect. Files that are
transitive dependencies of a `py_venv_binary` are scanned together in a single test,
giving `--pro` the full source closure for cross-file analysis.

Files not in any binary's dependency closure (orphans) keep individual per-file tests.

## Design Decisions

- **Python only** — Go services are out of scope for now.
- **Target the binary, not the image** — `py3_image` is a macro (aspects can't propagate
  through macros). `py_venv_binary` is a real rule with the same source closure.
- **Redundancy is acceptable** — A shared library scanned by multiple binary tests is fine;
  each binary gives different `--pro` cross-file context.
- **Correctness over deduplication** — Never miss a file an image depends on.
- **Orphans get individual tests** — Preserves fine-grained cache invalidation.

## Architecture

### New Starlark Components

**`rules_semgrep/aspect.bzl`:**

```starlark
SemgrepSourcesInfo = provider(
    fields = {"sources": "depset of Python source files"},
)
```

- `semgrep_source_aspect` — propagates through `deps` attribute, collects `.py` files
  from `srcs` and `main` attributes at each node.
- Filters out external files (`short_path` starting with `../`) to exclude `@pip//`
  dependencies.

**`rules_semgrep/target_test.bzl`:**

- `semgrep_target_test` — `rule(test = True)` that applies `semgrep_source_aspect` to
  its `target` attribute.
- Collects all transitive `.py` files from `SemgrepSourcesInfo`.
- Generates a launcher script invoking the existing `semgrep-test.sh` with all sources.
- Supports `rules`, `exclude_rules`, `pro_engine` — same interface as `semgrep_test`.

**`rules_semgrep/defs.bzl` (updated):**

```starlark
semgrep_test           # existing — srcs-based (rule validation, orphan files)
semgrep_target_test    # new — target-based with aspect
semgrep_manifest_test  # existing — Helm manifest scanning
```

### Aspect Propagation

```
semgrep_target_test(target = ":scraper")
    |
    v  aspect applied
py_venv_binary(name = "scraper", deps = [":scraper_main"])
    |
    v  aspect follows deps
py_library(name = "scraper_main", srcs = ["scraper_main.py"], deps = [":config", ...])
    |
    v  aspect follows deps (including cross-package)
py_library(name = "config", srcs = ["config.py"])
py_library(name = "models", srcs = ["models.py"])
...
@pip//fastapi  <-- filtered out (external, short_path starts with "../")
```

All `.py` files collected into a single `depset`, passed to `semgrep-test.sh`.

### Gazelle Extension Changes

**Algorithm (replaces per-file generation):**

```
1. Find py_venv_binary/py_binary targets in the BUILD file
2. For each: generate semgrep_target_test(target = ":binary_name")
3. Collect .py files that are main of a binary -> "covered"
4. Remaining .py files -> individual semgrep_test per file (current behavior)
5. No binaries in package -> all per-file semgrep_test (current behavior)
```

**Stale rule cleanup:** Existing per-file `semgrep_test` targets superseded by
`semgrep_target_test` are removed by the existing `staleRules()` mechanism.

**New rule kind:** Gazelle emits `semgrep_target_test` (in addition to `semgrep_test`).
Both kinds are tracked for stale rule cleanup.

**Directives unchanged:**
- `# gazelle:semgrep disabled` — skips all generation
- `# gazelle:semgrep_exclude_rules` — passed through to generated tests

### Example: knowledge_graph/app/

**Before (11 tests):**

```starlark
semgrep_test(name = "__init___semgrep_test", srcs = ["__init__.py"], ...)
semgrep_test(name = "chunker_semgrep_test", srcs = ["chunker.py"], ...)
semgrep_test(name = "config_semgrep_test", srcs = ["config.py"], ...)
semgrep_test(name = "embedder_main_semgrep_test", srcs = ["embedder_main.py"], ...)
semgrep_test(name = "mcp_main_semgrep_test", srcs = ["mcp_main.py"], ...)
semgrep_test(name = "models_semgrep_test", srcs = ["models.py"], ...)
semgrep_test(name = "notifications_semgrep_test", srcs = ["notifications.py"], ...)
semgrep_test(name = "qdrant_client_semgrep_test", srcs = ["qdrant_client.py"], ...)
semgrep_test(name = "scraper_main_semgrep_test", srcs = ["scraper_main.py"], ...)
semgrep_test(name = "storage_semgrep_test", srcs = ["storage.py"], ...)
semgrep_test(name = "telemetry_semgrep_test", srcs = ["telemetry.py"], ...)
```

**After (4 tests):**

```starlark
# Aspect-based: full cross-file context via --pro
semgrep_target_test(name = "scraper_semgrep_test", target = ":scraper", ...)
semgrep_target_test(name = "embedder_semgrep_test", target = ":embedder", ...)
semgrep_target_test(name = "mcp_semgrep_test", target = ":mcp", ...)

# Orphan: not a main of any binary
semgrep_test(name = "__init___semgrep_test", srcs = ["__init__.py"], ...)
```

**What each binary test scans (via aspect):**

| Test | Files scanned (transitive) |
|------|---------------------------|
| scraper | scraper_main.py, config.py, models.py, notifications.py, storage.py, telemetry.py, extractors/*.py |
| embedder | embedder_main.py, config.py, models.py, chunker.py, qdrant_client.py, storage.py, telemetry.py, embedders/*.py |
| mcp | mcp_main.py, config.py, models.py, qdrant_client.py, storage.py, telemetry.py, embedders/*.py |

Shared files (config.py, models.py, etc.) are scanned multiple times — each binary
provides different cross-file context for `--pro` analysis.

### Example: trips_api

**Before (3 tests):**

```starlark
semgrep_test(name = "__init___semgrep_test", srcs = ["__init__.py"], ...)
semgrep_test(name = "main_semgrep_test", srcs = ["main.py"], ...)
semgrep_test(name = "trips_api_test_semgrep_test", srcs = ["trips_api_test.py"], ...)
```

**After (3 tests):**

```starlark
semgrep_target_test(name = "main_semgrep_test", target = ":main", ...)
semgrep_test(name = "__init___semgrep_test", srcs = ["__init__.py"], ...)
semgrep_test(name = "trips_api_test_semgrep_test", srcs = ["trips_api_test.py"], ...)
```

Same count but `main_semgrep_test` now scans main.py with full dep context.

## Migration

- **No breaking changes** — `semgrep_test(srcs=...)` stays for rule validation and orphans.
- **Automatic migration** — `bazel run gazelle` regenerates BUILD files.
- **Single PR** — Gazelle regeneration updates all BUILD files at once.
- **Rollback** — Revert the Gazelle extension changes and re-run gazelle.

## Files Changed

| File | Change |
|------|--------|
| `rules_semgrep/aspect.bzl` | New: aspect + provider |
| `rules_semgrep/target_test.bzl` | New: test rule |
| `rules_semgrep/defs.bzl` | Export `semgrep_target_test` |
| `rules_semgrep/BUILD` | Add new bzl_library targets |
| `rules_semgrep/gazelle/generate.go` | Binary detection + target-based generation |
| `rules_semgrep/gazelle/generate_test.go` | Tests for new generation logic |
| `rules_semgrep/gazelle/config.go` | No changes expected |
| `services/*/BUILD` | Regenerated by gazelle |

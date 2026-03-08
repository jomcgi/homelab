# Configurable rules_semgrep Design

## Problem

The rules_semgrep Gazelle extension hardcodes:

1. **Binary kinds** — only `py_venv_binary` and `py_binary` get `semgrep_target_test` generation
2. **File extensions** — the aspect only collects `.py` files
3. **Rule configs** — Gazelle always emits `rules = ["//semgrep_rules:python_rules"]`

This prevents scanning `py3_image` targets (which wrap binaries) and blocks
future Go/multi-language support.

## Goal

Make rules_semgrep configurable via Gazelle directives so that:

- Any rule kind can trigger `semgrep_target_test` generation
- `py3_image` targets are scanned via their underlying binary
- The aspect collects all source files (not just `.py`)
- Language-specific rule configs are mapped via directive

## Design Decisions

- **Gazelle indirection for macros** — `py3_image` is a macro (aspects can't propagate
  through macros). Instead of converting it to a rule, Gazelle reads the `binary` attr
  and generates `semgrep_target_test(target = <binary>)`. Same coverage, zero changes
  to `py3_image.bzl`.
- **Aspect collects all files** — remove the `.py` extension hardcoding. Semgrep rules
  themselves determine what languages to scan. A `.go` file passed with Python rules is
  simply skipped.
- **Directive-driven** — target kinds and language mappings are configured via inheritable
  Gazelle directives, not hardcoded maps.
- **Image = security boundary** — if a `py3_image` pulls in files of multiple languages,
  semgrep should see them all.

## New Directives

### `# gazelle:semgrep_target_kinds`

```
# gazelle:semgrep_target_kinds py_venv_binary,py3_image
```

Comma-separated list of rule kinds that should get `semgrep_target_test` generation.
Inheritable through the directory tree. Default: `py_venv_binary`.

For each kind, Gazelle needs to know which attribute holds the target for the aspect.
Most kinds use the target itself. `py3_image` uses `binary`. This mapping is configured
in the kind definition:

```go
var kindTargetAttr = map[string]string{
    "py_venv_binary": "",       // target the rule itself
    "py3_image":      "binary", // follow binary attr
}
```

When `kindTargetAttr[kind]` is non-empty, Gazelle reads that attr from the BUILD rule
and uses it as the `semgrep_target_test` target. When empty, the rule itself is the target.

### `# gazelle:semgrep_languages`

```
# gazelle:semgrep_languages py
```

Comma-separated list of language keys. Each key maps to:

| Key  | Orphan extensions | Rules                          |
| ---- | ----------------- | ------------------------------ |
| `py` | `.py`             | `//semgrep_rules:python_rules` |
| `go` | `.go`             | `//semgrep_rules:go_rules`     |

Inheritable through directory tree. Default: `py`.

Controls:

- **Orphan detection** — which file extensions generate per-file `semgrep_test` when
  not covered by a binary
- **Rule configs** — which semgrep rule filegroups are passed as `rules`

For `semgrep_target_test`, ALL configured language rules are included (the image may
contain files from multiple languages). For per-file `semgrep_test`, only the matching
language's rules are used.

## Architecture Changes

### Aspect (`rules_semgrep/aspect.bzl`)

Remove `.py` extension filter. Collect all non-external source files:

```starlark
# Before:
if f.extension == "py" and not f.short_path.startswith("../"):

# After:
if not f.short_path.startswith("../"):
```

The provider stays the same but the field doc changes:

```starlark
SemgrepSourcesInfo = provider(
    doc = "Carries transitive source files for semgrep scanning.",
    fields = {"sources": "depset of source files from the main repository"},
)
```

### Gazelle Config (`config.go`)

Add new fields to `semgrepConfig`:

```go
type semgrepConfig struct {
    enabled      bool
    excludeRules []string
    targetKinds  map[string]string  // kind -> target attr ("" = self)
    languages    []string           // language keys
}
```

New directive handlers:

```go
case "semgrep_target_kinds":
    // Parse "py_venv_binary,py3_image" into targetKinds map
case "semgrep_languages":
    // Parse "py,go" into languages list
```

Defaults: `targetKinds = {"py_venv_binary": ""}`, `languages = ["py"]`.

### Gazelle Generate (`generate.go`)

Replace hardcoded `binaryKinds` with config-driven `targetKinds`:

```go
// Before:
var binaryKinds = map[string]bool{"py_venv_binary": true, "py_binary": true}

// After: read from cfg.targetKinds
```

For kinds with a target attr (like `py3_image.binary`), read the attr value from
the BUILD rule and use it as the `semgrep_target_test` target.

Language mapping for rules:

```go
var langRules = map[string]string{
    "py": "//semgrep_rules:python_rules",
    "go": "//semgrep_rules:go_rules",
}

var langExtensions = map[string]string{
    "py": ".py",
    "go": ".go",
}
```

### Gazelle Language (`language.go`)

Add new directives to `KnownDirectives()`:

```go
return []string{
    "semgrep",
    "semgrep_exclude_rules",
    "semgrep_target_kinds",
    "semgrep_languages",
}
```

## Propagation: How py3_image Targets Work

Given:

```starlark
# services/knowledge_graph/BUILD
py3_image(name = "scraper-image", binary = "//services/knowledge_graph/app:scraper")
```

With `# gazelle:semgrep_target_kinds py_venv_binary,py3_image` in root BUILD:

1. Gazelle finds `py3_image(name = "scraper-image")` in BUILD
2. Looks up `kindTargetAttr["py3_image"]` → `"binary"`
3. Reads `binary = "//services/knowledge_graph/app:scraper"` from the rule
4. Generates: `semgrep_target_test(target = "//services/knowledge_graph/app:scraper")`
5. Aspect propagates through the binary's deps, collects all source files
6. Semgrep scans everything with all configured language rules

## Example: Root BUILD Directives

```starlark
# gazelle:semgrep_target_kinds py_venv_binary,py3_image
# gazelle:semgrep_languages py
```

Future Go support:

```starlark
# gazelle:semgrep_target_kinds py_venv_binary,py3_image,go_binary
# gazelle:semgrep_languages py,go
```

## Migration

- **Backwards compatible** — default `targetKinds` = `py_venv_binary`, default
  `languages` = `py`. Existing behavior unchanged without new directives.
- **Opt-in** — add `py3_image` to `semgrep_target_kinds` in root BUILD to enable
  image-level scanning.
- **Single PR** — directive change + `bazel run gazelle` regenerates BUILD files.

## Files Changed

| File                                     | Change                                                |
| ---------------------------------------- | ----------------------------------------------------- |
| `rules_semgrep/aspect.bzl`               | Remove `.py` extension filter                         |
| `rules_semgrep/gazelle/config.go`        | Add `targetKinds`, `languages` config + directives    |
| `rules_semgrep/gazelle/generate.go`      | Config-driven kind detection, target attr indirection |
| `rules_semgrep/gazelle/generate_test.go` | Tests for new directive behavior                      |
| `rules_semgrep/gazelle/language.go`      | Register new directives                               |
| `rules_semgrep/gazelle/language_test.go` | Tests for new directives                              |
| `BUILD` (root)                           | Add `semgrep_target_kinds` directive                  |
| `services/*/BUILD`                       | Regenerated by gazelle                                |

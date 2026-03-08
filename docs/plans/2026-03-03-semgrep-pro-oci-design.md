# Semgrep Pro OCI Artifact Design

## Problem

Semgrep Pro engine and rule packs require an app token to download and are proprietary — they cannot be checked into Git. Bazel tests run in hermetic sandboxes without network access, so these artifacts must be pre-fetched and available as Bazel inputs. We need a caching and distribution mechanism that integrates with our existing Bazel + OCI tooling.

## Decision

Publish Semgrep Pro engine and rule packs as separate OCI artifacts on GHCR, pinned by digest in a single Bazel file. An automated daily GitHub Actions workflow detects upstream changes, pushes updated artifacts, and opens an automerge PR to update digests.

## Artifact Structure

Separate OCI artifacts at `ghcr.io/jomcgi/homelab/tools/semgrep-pro/`:

| Artifact           | Content                                        | Platforms                    |
| ------------------ | ---------------------------------------------- | ---------------------------- |
| `engine`           | Pro engine binary (`semgrep-core-proprietary`) | `linux/amd64`, `linux/arm64` |
| `rules/golang`     | Go rule YAML files                             | Platform-independent         |
| `rules/python`     | Python rule YAML files                         | Platform-independent         |
| `rules/javascript` | JavaScript rule YAML files                     | Platform-independent         |
| `rules/kubernetes` | Kubernetes rule YAML files                     | Platform-independent         |

### Why separate artifacts?

Bazel repository rules cache at the digest level. A single monolithic artifact means changing one Go rule forces re-fetch of everything and re-analysis of all semgrep test targets. Separate artifacts give:

- **Granular fetch** — only download what changed
- **Granular re-analysis** — Go rule update only re-analyzes Go scan targets
- **Independent update cadence** — engine updates monthly, rules update more frequently
- **Clean dependency graph** — Go services cannot transitively depend on Python rules

### Versioning

Tags use timestamps for human reference (e.g., `20260303`). Tags are mutable — re-running the workflow on the same day overwrites the tag. **Digests are the source of truth** in the repository.

## Bazel Integration

### Digest pin file — `third_party/semgrep_pro/digests.bzl`

```starlark
SEMGREP_PRO_DIGESTS = {
    "engine": "sha256:abc123...",
    "rules_golang": "sha256:def456...",
    "rules_python": "sha256:789aaa...",
    "rules_javascript": "sha256:bbb111...",
    "rules_kubernetes": "sha256:ccc222...",
}
```

Single file. Easy to template. All digest churn is isolated here.

### Module extension — `third_party/semgrep_pro/extensions.bzl`

Reads `digests.bzl` and creates repository rules that:

1. Fetch each artifact using `crane export <image>@<digest>`
2. Extract into a directory tree
3. Generate BUILD files with per-artifact filegroups

Results are cached by Bazel's repository cache — only re-fetched when digests change.

### Consuming in rules_semgrep

The existing `semgrep_test` and `semgrep_manifest_test` rules gain support for:

- Pro engine binary as an additional tool dep alongside OSS `semgrep`
- Pro rule filegroups as additional `rules` entries

```starlark
semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.go"]),
    rules = [
        "//semgrep_rules:pro_golang_rules",  # pro rules
        "//semgrep_rules:bazel_rules",       # custom rules (existing)
    ],
)
```

### Cache invalidation matrix

| What changed      | Go scan     | Python scan | K8s scan    |
| ----------------- | ----------- | ----------- | ----------- |
| Go source file    | **re-runs** | cached      | cached      |
| Go pro rule       | **re-runs** | cached      | cached      |
| Python pro rule   | cached      | **re-runs** | cached      |
| Pro engine binary | **re-runs** | **re-runs** | **re-runs** |
| Nothing           | cached      | cached      | cached      |

## Automated Update Pipeline

### GitHub Actions workflow — `.github/workflows/update-semgrep-pro.yaml`

Trigger: daily schedule + manual `workflow_dispatch`.

```
1. Download pro engine + rules
   - SEMGREP_APP_TOKEN from repo secret
   - semgrep install-semgrep-pro (engine for both platforms)
   - semgrep --dump-config p/golang, p/python, p/javascript, p/kubernetes

2. Package per-language artifacts
   - tar + crane push for each artifact
   - Tag: YYYYMMDD timestamp

3. Collect new digests
   - crane digest for each pushed artifact

4. Diff against third_party/semgrep_pro/digests.bzl
   - If all digests match → exit early (no noise)

5. Update digests.bzl
   - Template new sha256 values into the file

6. Commit + PR + automerge
   - Branch: update/semgrep-pro-YYYYMMDD
   - gh pr create
   - gh pr merge --auto --rebase
```

### Safety properties

- **Early exit on no diff** — no PR noise when nothing changed
- **Atomic PR** — one PR updates all changed digests together
- **CI validates** — BuildBuddy runs `bazel test //...` confirming new artifacts are fetchable and tests pass
- **Automerge with rebase** — matches repo merge policy
- **No secrets in repo** — `SEMGREP_APP_TOKEN` is a repo secret, digests are the only thing committed

## What doesn't change

- Custom rules in `semgrep_rules/` continue working as-is
- `argocd_app` macro's `semgrep_rules` parameter still works
- OSS semgrep stays as the pip dependency — pro engine augments it
- Pre-commit hook stays on OSS (pro engine is for CI depth only)
- Existing `semgrep_test` targets keep working — pro is additive

## Components to implement

1. `third_party/semgrep_pro/digests.bzl` — digest pin file
2. `third_party/semgrep_pro/extensions.bzl` — module extension (fetch + extract)
3. `third_party/semgrep_pro/BUILD` — bzl_library exports
4. MODULE.bazel changes — register the module extension
5. `rules_semgrep` updates — support pro engine in test runners
6. `.github/workflows/update-semgrep-pro.yaml` — automated pipeline
7. CI validation — ensure BuildBuddy can pull private GHCR artifacts during fetch

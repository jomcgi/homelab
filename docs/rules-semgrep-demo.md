# rules_semgrep: Deterministic SAST in Bazel

## The Problem

Semgrep's default CLI (pysemgrep) adds 2-4s of Python startup overhead per invocation, isn't hermetic, and can't participate in Bazel's content-addressed cache. In a monorepo with dozens of scan targets, this means:

- Non-deterministic builds (network calls, version drift)
- Slow CI (every scan re-runs, even on unchanged files)
- Manual BUILD file maintenance for scan targets

## The Solution: rules_semgrep

Three components working together:

```
┌──────────────────────────────────────────────────────────────┐
│                    OCI Artifact Pipeline                      │
│  Daily: download engines + rules → content-hash → push GHCR  │
│  digests.bzl pins every artifact by sha256 manifest digest    │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                      Bazel Rules                              │
│  semgrep_test          — scan explicit file list              │
│  semgrep_target_test   — scan target's transitive sources     │
│  semgrep_manifest_test — render Helm chart, scan YAML         │
│                                                               │
│  All invoke semgrep-core directly (no pysemgrep)              │
│  Inputs: sources + rules + engine binary → content-addressed  │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                   Gazelle Extension                           │
│  Auto-generates semgrep BUILD targets from existing code      │
│  Zero manual maintenance — just run `bazel run gazelle`       │
└──────────────────────────────────────────────────────────────┘
```

---

## 1. Deterministic Semgrep

Every input is pinned by content hash. No network calls at scan time.

**Engine binaries** — extracted from PyPI wheels (OSS) and Semgrep API (Pro), pushed to GHCR as OCI artifacts with content-addressed tags:

```python
# third_party/semgrep_pro/digests.bzl (auto-updated daily)
SEMGREP_PRO_DIGESTS = {
    "engine_amd64":  "sha256:9b9cc77cf65d...",
    "engine_arm64":  "sha256:30076cf5af48...",
    "rules_python":  "sha256:6cf429baea5d...",
    "rules_kubernetes": "sha256:eaeeeff194ba...",
    # ...11 artifacts total
}
```

**Content-addressed tagging** — identical artifacts produce identical digests, even across daily runs:

```bash
# In update-semgrep-pro.yaml
content_hash() {
  (cd "$1" && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
}
hash=$(content_hash artifacts/engine-amd64)
content_tag="content-${hash:0:16}"

# Skip push if content unchanged
crane digest ghcr.io/.../engine-amd64:${content_tag} && echo "Already exists"
```

If the Semgrep team doesn't release a new version, the daily job detects identical content and skips the push entirely. **Digest stays stable. Cache stays warm.**

**Custom rules** — version controlled in `semgrep_rules/`:

```yaml
# semgrep_rules/python/no-eval-exec.yaml
rules:
  - id: no-eval-exec
    languages: [python]
    severity: ERROR
    message: >-
      Avoid dynamic code execution, use ast.literal_eval() for data parsing.
    pattern-either:
      - pattern: eval(...)
      - pattern: exec(...)
```

---

## 2. Cache Management

Bazel computes a content hash of all test inputs. If nothing changed, the test doesn't re-run.

**Inputs that form the cache key:**

| Input | Source |
|-------|--------|
| Source files | `srcs` attribute or aspect-collected transitive closure |
| Rule YAML files | `rules` attribute (custom + vendored Pro rules) |
| SCA advisory rules | `sca_rules` attribute (supply chain rules) |
| Lockfiles | `lockfiles` attribute (requirements.txt, go.sum, pnpm-lock.yaml) |
| Engine binary | `//third_party/semgrep_pro:engine` (digest-pinned OCI artifact) |
| Test runner | `semgrep-test.sh` |
| Exclude rules | `SEMGREP_EXCLUDE_RULES` env var |

**What triggers a re-scan:**

```
Edit scrape.py         → source hash changes    → re-run
Edit rule YAML         → rule hash changes      → re-run
New semgrep release    → engine digest changes   → re-run
Add @pip// dep         → aspect sees new sources → re-run
Change exclude_rules   → env var changes         → re-run
```

**What doesn't (cache hit):**

```
Rename test target     → inputs unchanged → cache hit
Edit unrelated file    → not in srcs      → cache hit
Re-run same commit     → all hashes match → cache hit
```

---

## 3. Developer Impact: Gazelle-Managed

Developers never write semgrep BUILD targets by hand. Gazelle auto-generates them.

**Before (manual):** Every new Python file or target needs a hand-written scan target.

**After (Gazelle):** Run `bazel run gazelle` and BUILD files update automatically.

### How it works

Given this existing target:

```python
# services/hikes/scrape_walkhighlands/BUILD
py_venv_binary(
    name = "scrape",
    srcs = ["scrape.py"],
    main = "scrape.py",
    deps = [
        ":scrape_walkhighlands",  # local library
        "@pip//requests",         # external dep → triggers SCA
        "@pip//beautifulsoup4",
    ],
)
```

Gazelle generates:

```python
# Auto-generated — scans scrape target's full transitive source tree
semgrep_target_test(
    name = "scrape_semgrep_test",
    exclude_rules = ["no-requests"],
    lockfiles = ["//requirements:all.txt"],   # detected from @pip// deps
    rules = ["//semgrep_rules:python_rules"],
    sca_rules = ["//semgrep_rules:sca_python_rules"],  # detected from lockfile
    target = ":scrape",
)

# Auto-generated — orphan file not covered by any target's deps
semgrep_test(
    name = "scrape_test_semgrep_test",
    srcs = ["scrape_test.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)
```

**Key behaviours:**

- **Target detection:** Finds `py_venv_binary` (configurable via `# gazelle:semgrep_target_kinds`)
- **SCA detection:** Sees `@pip//` in deps → adds pip lockfile + SCA advisory rules
- **Orphan detection:** Test files not transitively reachable from any target get their own `semgrep_test`
- **Directive inheritance:** `# gazelle:semgrep_exclude_rules no-requests` propagates to all generated targets
- **Stale cleanup:** Removes targets for deleted files automatically

---

## 4. What Semgrep Actually Scans

Semgrep doesn't scan "the whole repo." It scans **exactly the files Bazel tells it to.**

### semgrep_target_test — Aspect-driven transitive sources

A Bazel [aspect](https://bazel.build/extending/aspects) walks the target's real dependency graph:

```
semgrep_target_test(target = ":scrape")
         │
         ▼ aspect walks deps
    ┌────────────┐
    │  :scrape   │ → scrape.py (srcs + main)
    │  deps:     │
    │   :scrape_walkhighlands ──→ __init__.py, error_handling.py, scrape.py
    │   @pip//requests ──→ (external, skipped)
    └────────────┘

    Result: semgrep scans exactly [scrape.py, __init__.py, error_handling.py]
```

The aspect (`aspect.bzl`) collects `srcs` and `main` attributes from each dep, skipping external dependencies (`short_path.startswith("../")`). This gives semgrep-core's `--pro_inter_file` flag the right file set for cross-file dataflow analysis.

### semgrep_test — Explicit file list

For orphan files (tests, scripts) not reachable from any target:

```python
semgrep_test(
    srcs = ["scrape_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

Scans exactly that file, nothing more.

### semgrep_manifest_test — Rendered Helm output

For Kubernetes policy:

```python
semgrep_manifest_test(
    chart = "charts/todo",
    release_name = "todo",
    namespace = "prod",
    values_files = ["values.yaml"],
    rules = ["//semgrep_rules:kubernetes_rules"],
)
```

Runs `helm template` → scans the rendered YAML. Catches misconfiguration that only appears after values substitution.

---

## 5. Cache Invalidation Demo: New Rule on a PR

**Scenario:** Add a new Python rule that blocks `print()` statements, push on a PR.

### Step 1: Add the rule

```yaml
# semgrep_rules/python/no-print.yaml
rules:
  - id: no-print
    languages: [python]
    severity: WARNING
    message: Use logging module instead of print()
    pattern: print(...)
```

### Step 2: What happens in CI

```
1. PR pushed
2. `bazel test //...` starts
3. Bazel computes cache keys for every semgrep test:
   - //semgrep_rules:python_rules filegroup now includes no-print.yaml
   - Hash of python_rules changed
   - ALL Python semgrep tests invalidated (rules are a shared input)
4. Every Python semgrep_test and semgrep_target_test re-runs
5. Any file with print() → finding → test FAILS → PR blocked
```

**This is the key insight:** changing a rule YAML invalidates every test that depends on `//semgrep_rules:python_rules`, but does NOT invalidate Go tests, Kubernetes manifest tests, or anything else. **Invalidation is precise to the dependency graph.**

### What DOESN'T invalidate

```
- Go semgrep tests        → different rules filegroup    → cache hit
- Kubernetes manifest tests → different rules filegroup  → cache hit
- Unit tests              → no semgrep dependency at all → cache hit
- Unrelated Python tests  → same sources, same rules    → wait, rules changed → re-run
```

### Blocking findings

If any `print()` call exists in scanned Python files, the semgrep test exits non-zero and the PR cannot merge. The finding appears in the test output:

```
FINDING: no-print
  File: services/hikes/scrape_walkhighlands/scrape.py:42
  Message: Use logging module instead of print()
  Severity: WARNING
```

To fix: either remove the `print()` call, or add `no-print` to `exclude_rules` in the BUILD directive:

```
# gazelle:semgrep_exclude_rules no-requests,no-print
```

---

## 6. Merge Queue Compatibility

Because semgrep tests are just regular `bazel test` targets, they participate in Bazel's remote cache alongside unit tests, integration tests, and everything else.

**In a merge queue (or stacked PRs):**

```
PR #1: edit scrape.py           → semgrep re-runs for scrape targets
PR #2: edit ships_api/main.go   → semgrep re-runs for Go targets only
PR #3: docs-only change         → all semgrep tests cache-hit

Merge queue rebases PR #2 onto PR #1:
  - scrape targets: already cached from PR #1 → hit
  - ships_api targets: already cached from PR #2 → hit
  - everything else: unchanged → hit
```

**Low latency by design:**

| Scenario | Latency |
|----------|---------|
| Cache hit (nothing changed) | **0s** — test marked passed immediately |
| Cache miss (source changed) | **2-8s** — semgrep-core Pro runs directly, no pysemgrep startup |
| Cold cache (new rule) | **2-8s per target** — parallelized across Bazel workers |

Compare to pysemgrep CLI: 2-4s Python startup overhead **per invocation**, plus non-deterministic network calls for rules/engine. On a repo with 30+ scan targets, that's minutes vs seconds.

**Key property:** semgrep tests don't have special CI treatment. They're cached, parallelized, and scheduled by Bazel alongside every other test. A merge queue rebase that doesn't touch your files produces an instant cache hit.

---

## Architecture Summary

```
Developer writes code
        │
        ▼
  `bazel run gazelle`
  Auto-generates semgrep_test / semgrep_target_test / semgrep_manifest_test
        │
        ▼
  `bazel test //...`  (CI or local)
        │
        ├─ Cache hit? → pass instantly (0s)
        │
        └─ Cache miss? → semgrep-core Pro runs (~2-8s)
                │
                ├─ SAST: interfile analysis on transitive sources
                ├─ SCA: lockfile dependency scanning
                └─ Manifest: rendered Helm YAML policy checks
                         │
                         ▼
                  Finding? → test FAILS → PR blocked
                  Clean?   → test passes → cached for next run
```

**Zero developer friction.** No semgrep CLI to install. No config files to maintain. No CI jobs to manage. Just `bazel test //...` — semgrep is part of the build.

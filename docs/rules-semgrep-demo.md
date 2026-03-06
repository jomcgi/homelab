# rules_semgrep: Deterministic SAST in Bazel

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

## Deterministic Semgrep

Every input is digest-pinned. No network calls at scan time. No pysemgrep.

```python
# third_party/semgrep_pro/digests.bzl (auto-updated daily)
SEMGREP_PRO_DIGESTS = {
    "engine_amd64":     "sha256:9b9cc77cf65d...",
    "rules_python":     "sha256:6cf429baea5d...",
    "rules_kubernetes": "sha256:eaeeeff194ba...",
    # ...11 artifacts total
}
```

Daily CI downloads engines + rules, computes a content hash, and skips the push if nothing changed. **Same content = same digest = warm cache.**

---

## Cache Management

Bazel hashes all test inputs. If nothing changed, the test doesn't re-run.

```
Edit scrape.py         → source hash changes    → re-run
Edit rule YAML         → rule hash changes      → re-run
New semgrep release    → engine digest changes   → re-run
Edit unrelated file    → not in input set        → cache hit
Re-run same commit     → all hashes match        → cache hit
```

---

## Gazelle-Managed BUILD Files

Developers never write semgrep targets. Given an existing target:

```python
py_venv_binary(
    name = "scrape",
    srcs = ["scrape.py"],
    deps = [":scrape_walkhighlands", "@pip//requests", "@pip//beautifulsoup4"],
)
```

`bazel run gazelle` auto-generates:

```python
semgrep_target_test(
    name = "scrape_semgrep_test",
    target = ":scrape",
    rules = ["//semgrep_rules:python_rules"],
    lockfiles = ["//requirements:all.txt"],       # detected from @pip// deps
    sca_rules = ["//semgrep_rules:sca_python_rules"],
    exclude_rules = ["no-requests"],              # from gazelle directive
)
```

Orphan files (tests not in any target's dep tree) get their own `semgrep_test` automatically.

---

## What Semgrep Actually Scans

A Bazel aspect walks the target's dependency graph and collects transitive sources:

```
semgrep_target_test(target = ":scrape")
         │
         ▼ aspect walks deps
    ┌────────────┐
    │  :scrape   │ → scrape.py
    │   :scrape_walkhighlands ──→ __init__.py, error_handling.py
    │   @pip//requests ──→ (external, skipped)
    └────────────┘
    Scans exactly: [scrape.py, __init__.py, error_handling.py]
```

This feeds semgrep-core's `--pro_inter_file` for cross-file dataflow — scoped to real dependencies, not the whole repo.

---

## Cache Invalidation: New Rule on a PR

Add a rule, push to a PR, watch it cascade:

```yaml
# semgrep_rules/python/no-print.yaml
rules:
  - id: no-print
    languages: [python]
    severity: WARNING
    message: Use logging module instead of print()
    pattern: print(...)
```

```
PR pushed → bazel test //...
  //semgrep_rules:python_rules filegroup changed (new YAML)
  → ALL Python semgrep tests invalidated → re-run
  → Go / Kubernetes tests: different rules filegroup → cache hit
  → Unit tests: no semgrep dep → cache hit
  → Any print() found → test FAILS → PR blocked
```

Invalidation is precise to the dependency graph.

---

## Merge Queue Compatibility

Semgrep tests are regular `bazel test` targets — cached and parallelized alongside everything else.

```
PR #1: edit scrape.py         → semgrep re-runs for scrape targets
PR #2: edit ships_api/main.go → semgrep re-runs for Go targets only
PR #3: docs-only change       → all semgrep tests cache-hit

Merge queue rebases PR #2 onto PR #1:
  scrape targets:    cached from PR #1  → hit
  ships_api targets: cached from PR #2  → hit
  everything else:   unchanged          → hit
```

| Scenario | Latency |
|----------|---------|
| Cache hit | **0s** — instant pass |
| Cache miss | **2-8s** — semgrep-core Pro, no pysemgrep overhead |

No special CI treatment. A merge queue rebase that doesn't touch your files = instant cache hit.

---

```
Developer writes code
        │
        ▼
  `bazel run gazelle`  →  auto-generates scan targets
        │
        ▼
  `bazel test //...`
        │
        ├─ Cache hit  → 0s
        └─ Cache miss → semgrep-core Pro (~2-8s)
                │
                ├─ SAST: interfile analysis on transitive sources
                ├─ SCA: lockfile dependency scanning
                └─ Manifest: rendered Helm YAML policy checks
                         │
                         ▼
                  Finding → PR blocked
                  Clean   → cached for next run
```

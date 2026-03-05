# Design: rules_semgrep Diagrams & Documentation

**Author:** Joe McGinley
**Created:** 2026-03-04

---

## Goal

Two concise, diagram-rich documents that explain `rules_semgrep` to Bazel power users:

1. **ADR** (`architecture/decisions/security/001-bazel-semgrep.md`) — the *why*: reproducible build chain + CI speed for agentic workflows
2. **README** (`rules_semgrep/README.md`) — the *what/how*: API reference + scanning methodology

Both target Bazel-literate developers. Tone is punchy/technical, not marketing.

---

## Pitch (core message)

Semgrep Pro rules on your own infrastructure. Cache invalidation on your own terms. No pip install, no registry fetches, no Python wrapper — just a hermetic OCaml binary pinned to a digest.

---

## Document 1: ADR — `architecture/decisions/security/001-bazel-semgrep.md`

New `security/` category alongside `agents/`, `docs/`, `networking/`.

### Structure (tight 1-page)

| Section | Content |
|---|---|
| **Problem** | Agentic workflows need fast, deterministic CI. Semgrep via pip/pre-commit breaks both: 2m+ diff scans, 5m+ full scans on managed infra. Python wrapper adds 2-4s/invocation, registry fetches are non-deterministic. |
| **Proposal** | 3-layer architecture: OCI-vendored binaries -> Bazel rules -> Gazelle auto-generation. Mermaid diagram showing daily-update -> build -> scan pipeline. |
| **Key Decisions** | Compact table: bypass Python (direct semgrep-core), vendor via OCI (digest-pinned), no-sandbox (100x speedup), aspect for transitive deps, graceful degradation (empty filegroup -> SKIP), Gazelle auto-gen |
| **Results** | Before: 2m+ diff, 5m+ full (managed infra). After: 30s small change, 50s new rules, 4m cold cache full build+test+images+semgrep. |

### Mermaid: Architecture Pipeline

```
graph TD
    subgraph "Daily Update (GitHub Actions)"
        PYPI[PyPI Wheels] --> EXTRACT[Extract semgrep-core]
        SEMGREP_API[Semgrep API] --> PRO[Pro Engine + Rules]
        EXTRACT --> GHCR[GHCR OCI Artifacts]
        PRO --> GHCR
    end

    subgraph "Bazel Analysis (bzlmod)"
        GHCR -->|digest-pinned| REPO_RULE[oci_archive repo rule]
        REPO_RULE --> ENGINE[Platform-specific binary]
    end

    subgraph "Bazel Test Execution"
        ENGINE --> SCAN[semgrep-core scan]
        SRCS[Source files] --> SCAN
        RULES[Rule YAML] --> SCAN
        SCAN -->|cached until inputs change| RESULT[Pass / Fail]
    end
```

---

## Document 2: README — `rules_semgrep/README.md`

### Structure

| Section | Content |
|---|---|
| **Pitch** | 3 lines: what it is, why it exists, the key insight (Bazel cache invalidation = scan only what changed) |
| **How It Works** | Mermaid diagram: scan flow from source -> aspect -> semgrep-core -> results |
| **Rules** | 3 rule types as compact table: `semgrep_test`, `semgrep_manifest_test`, `semgrep_target_test` with one-liner + example each |
| **Gazelle** | Directive table + "auto-generates scan targets" explanation |
| **Rule Files** | Table of custom + Pro rule categories |
| **Pro Engine** | Graceful degradation: no token -> empty filegroup -> SKIP (2 sentences) |
| **Platform Support** | 4-platform select() table (linux/macOS x amd64/arm64) |

### Mermaid: Scan Flow

```
graph LR
    subgraph "semgrep_target_test"
        TARGET[":server"] -->|aspect walks deps| ASPECT[SemgrepSourcesInfo]
        ASPECT --> SRCS[Transitive sources]
    end

    SRCS --> CORE["semgrep-core --pro"]
    RULE_YAML[Rule YAML] --> CORE
    CORE --> RESULTS{Findings?}
    RESULTS -->|none| PASS[PASS]
    RESULTS -->|findings| FAIL[FAIL + details]
    RESULTS -.->|best-effort| UPLOAD[Semgrep App]
```

---

## Constraints

- ADR follows existing convention (see `004-autonomous-agents.md` for format: Problem / Proposal / sections)
- README is API-focused — concise prose, tables over paragraphs, examples over explanation
- Mermaid diagrams must render in GitHub markdown
- No emojis in documents
- Conventional Commits for the PR

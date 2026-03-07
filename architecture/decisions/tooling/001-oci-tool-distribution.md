# ADR 001: OCI-Based Tool Distribution

**Author:** Joe McGinley
**Status:** Draft
**Created:** 2026-03-07

---

## Problem

The homelab repo uses Bazel for everything — builds, tests, formatting, image pushing, and developer tool management. The `bazel_env` rule in `tools/BUILD` builds ~20 tools (helm, crane, go, node, pnpm, buildifier, etc.) and symlinks them into a `bin/` directory that `.envrc` adds to `$PATH`. This creates three problems:

1. **Bazel is required for basic development** — Even viewing Helm templates or running `format` requires a working Bazel installation, toolchain download, and repository rule resolution. On an M-series Mac, `bazel run //tools:bazel_env` takes ~45 seconds on a warm cache and minutes on a cold one.

2. **No tool parity between environments** — Local development (macOS/aarch64), CI (Linux/x86_64), and Goose agent sandboxes (Linux/x86_64) each resolve tool versions independently. The Goose agent image (`charts/goose-agent/image/apko.yaml`) packages its own copies of `go`, `node`, `pnpm`, etc. — there's no guarantee these match what `bazel_env` provides locally.

3. **Local Bazel execution is inefficient** — Running `bazel test //...` or `bazel build //...` locally downloads the full Bazel toolchain, resolves all external dependencies, and executes on a single machine. BuildBuddy remote execution is faster (parallelism, shared caching, beefy runners) and already runs on every push via `buildbuddy.yaml`.

---

## Proposal

Eliminate local Bazel entirely. Distribute developer tools as a multi-arch OCI image built in CI and pulled locally via Docker/Podman. All builds, tests, and formatting run remotely via BuildBuddy — triggered by pushing code rather than executing locally.

### Before and After

| Aspect                   | Today                                          | Proposed                                                    |
| ------------------------ | ---------------------------------------------- | ----------------------------------------------------------- |
| Developer tool setup     | `bazel run //tools:bazel_env` (~45s warm)       | `docker pull` + extract (~5s)                                |
| Tool versions            | Resolved independently per environment          | Single multi-arch OCI image, identical everywhere            |
| Running tests            | `bazel test //...` (local execution)            | Push → BuildBuddy remote execution → MCP to observe results |
| Formatting               | `bazel run //tools/format:fast_format` (local)  | Push → CI format job → auto-commit fixes back                |
| Build graph queries      | `bazel query` (local)                           | `bb query` (remote via BuildBuddy) or BuildBuddy MCP tools   |
| Goose tool availability  | Separate apko image with its own tool versions  | Same OCI tools image, shared versions                        |
| Claude Code version      | Installed independently per machine              | Pinned in tools image, identical across all environments     |
| Bazel on dev machine     | Required                                        | Not required                                                 |

---

## Architecture

### OCI Tools Image

A single multi-arch (x86_64 + aarch64) OCI image containing all developer tools:

```
ghcr.io/jomcgi/homelab-tools:latest

/tools/bin/
├── helm              # Helm CLI (from multitool)
├── crane             # OCI image tool (from multitool)
├── kind              # Local K8s clusters (from multitool)
├── argocd            # ArgoCD CLI (from multitool)
├── buildifier        # Starlark formatter (from multitool)
├── buildozer         # BUILD file editor (from multitool)
├── op                # 1Password CLI (from multitool)
├── go                # Go toolchain
├── node              # Node.js runtime
├── pnpm              # Node package manager
├── python            # Python runtime
├── bb                # BuildBuddy CLI (for remote query/execution)
├── scaffold          # Scaffold code generator
├── copier            # Project templating
└── claude            # Claude Code CLI (via npm, @anthropic-ai/claude-code)
```

Built via apko (consistent with all other images in the repo), pushed to GHCR on every merge to main.

Claude Code is included as a first-class tool — it's installed via `pnpm add -g @anthropic-ai/claude-code` during the image build. This gives:
- **Pinned versions** across local dev, CI, and in-cluster agents
- **Goose replacement path** — in-cluster agents could run Claude Code directly instead of Goose, using the same skills, hooks, and CLAUDE.md from the repo
- **Consistent MCP configuration** — the `.mcp.json` and `.claude/` configs ship with the repo, and the CLI version matches what was tested against them

### Tool Pull Mechanism

Local `.envrc` replaces the `bazel_env` integration:

```bash
TOOLS_IMAGE="ghcr.io/jomcgi/homelab-tools:latest"
TOOLS_DIR="$PWD/.tools"

# Pull tools if missing or stale (>24h)
if [[ ! -d "$TOOLS_DIR/bin" ]] || find "$TOOLS_DIR/.pulled" -mtime +1 -print -quit 2>/dev/null | grep -q .; then
  echo "Pulling developer tools from $TOOLS_IMAGE..."
  docker run --rm --platform "$(uname -m)" \
    -v "$TOOLS_DIR:/out" "$TOOLS_IMAGE" \
    cp -r /tools/. /out/
  touch "$TOOLS_DIR/.pulled"
fi

PATH_add "$TOOLS_DIR/bin"
```

The `.tools/` directory is gitignored. Tools are refreshed daily or on demand.

### Goose Integration

The Goose agent image (`charts/goose-agent/image/apko.yaml`) currently packages its own tools. Two options:

**Option A — Multi-stage copy:** The goose-agent apko image copies binaries from the tools image. Tool versions are guaranteed identical because they come from the same source.

**Option B — Base image:** The goose-agent image uses `homelab-tools` as its base, adding goose-specific packages on top.

Option A is preferred — it's more explicit and doesn't couple the goose image lifecycle to the tools image.

### Remote Execution Workflow

All Bazel operations execute remotely. The developer workflow becomes:

```
Edit code
    │
    ▼
git push (to feature branch)
    │
    ├──▶ BuildBuddy CI triggers automatically
    │    ├── Format check (formatters + gazelle)
    │    ├── Test suite (bazel test //...)
    │    └── Image push (main branch only)
    │
    ▼
Observe results via:
    ├── BuildBuddy MCP tools (buildbuddy-mcp-get-invocation, get-log, get-target)
    ├── GitHub PR checks (gh pr checks)
    └── BuildBuddy web UI (links in BES output)
```

### Remote Format Workflow

Today, `format` runs locally via `bazel run //tools/format:fast_format`. In the new model:

1. Developer pushes to a branch
2. CI "Format check" job runs formatters + gazelle
3. If changes are needed, CI commits them back to the branch
4. Developer pulls the format fixes

This is slower than local formatting but eliminates the need for local Bazel entirely. The CI format job already exists in `buildbuddy.yaml` — it just needs to commit fixes back instead of failing.

### Build Graph Queries

For `bazel query` (dependency inspection, target discovery):

- **`bb query`** — The BuildBuddy CLI can execute queries remotely via BuildBuddy RBE. Include `bb` in the tools image for this.
- **BuildBuddy MCP tools** — `buildbuddy-mcp-get-target` provides target-level information from recent invocations.
- **`bazel query` in CI** — For complex queries, push a script that runs the query in CI and outputs results.

Most query needs are covered by `bb query` running remotely.

### Missing Tools & Workflow Gaps

The OCI tools image is an opportunity to close gaps in the current `bazel_env` setup. These tools are either used in workflows but not distributed, or represent workflow gaps that should be filled:

#### Currently missing from `bazel_env`

| Tool | Current status | Why it should be in the tools image |
| ---- | -------------- | ----------------------------------- |
| `gh` | In goose-agent apko image, not in `bazel_env` | Essential for PR workflow (`gh pr create`, `gh pr merge --auto --rebase`) |
| `ruff` | Only runs via Bazel lint aspect | Useful for quick local Python linting without remote execution |
| `shellcheck` | Only runs via Bazel lint aspect | Useful for quick local shell script linting |
| `eslint` | Only runs via Bazel lint aspect | Useful for quick local JS linting |
| `agent-run` | Custom Go binary in `tools/agent-run/` | CLI for triggering Goose agent tasks — needs to be available locally |
| `hf2oci` | Custom Go binary in `tools/hf2oci/` | CLI for HuggingFace model → OCI conversion |
| `claude` | Installed independently per machine via npm | Claude Code CLI — pinning version ensures skills, hooks, and MCP config are tested against a known version. Enables in-cluster agents to run Claude Code directly. |

#### Workflow gaps (new tooling needed)

| Workflow | Gap | Proposed solution |
| -------- | --- | ----------------- |
| **ArgoCD app diffing** | `rules_helm/app.bzl` has a `diff` rule referencing `argocd-live-diff.sh`, but the script doesn't exist. No way to preview what a values.yaml change will do to the live cluster. | Create the diff script. Include `argocd` CLI in the tools image (already in multitool). The script should: render local Helm template → diff against live ArgoCD app manifests. Can also be exposed as an MCP tool via Context Forge. |
| **Manifest preview** | `render_manifests` requires Bazel to run `helm template`. Without local Bazel, developers can't preview rendered manifests before pushing. | `helm` is already in the tools image. Create a standalone `render` script that calls `helm template` directly with the right flags, without Bazel wrapping. |
| **Lint without Bazel** | Linters (`ruff`, `shellcheck`, `eslint`) only run via Bazel aspects. Can't lint a single file quickly. | Include linter binaries in the tools image. Add a `lint` script that runs them directly on changed files. |

---

## Implementation

### Phase 1: OCI Tools Image

- [ ] Create `tools/image/apko.yaml` with all tools currently in `bazel_env` plus missing tools (`gh`, `ruff`, `shellcheck`, `eslint`)
- [ ] Include custom Go binaries (`agent-run`, `hf2oci`) — built in CI, copied into image
- [ ] Create `tools/image/BUILD` with apko build + push rules
- [ ] Add `homelab-tools` image push to `buildbuddy.yaml` CI pipeline (push on main)
- [ ] Add ArgoCD Image Updater config for automatic digest updates
- [ ] Verify multi-arch (x86_64 + aarch64) build works

### Phase 2: Local Bootstrap

- [ ] Update `.envrc` to pull tools from GHCR instead of `bazel_env`
- [ ] Add `.tools/` to `.gitignore`
- [ ] Add a `bootstrap.sh` script for first-time setup (validates docker/podman, pulls image)
- [ ] Update `README.bazel.md` to reflect new workflow
- [ ] Remove `bazel_env` rule from `tools/BUILD` (or deprecate)

### Phase 3: Standalone Workflow Scripts

- [ ] Create `argocd-live-diff.sh` — renders local Helm template, diffs against live ArgoCD app manifests
- [ ] Create standalone `render` script — calls `helm template` directly without Bazel
- [ ] Create standalone `lint` script — runs ruff/shellcheck/eslint on changed files
- [ ] Wire diff script into `rules_helm/app.bzl` (completing the existing `generate_diff` infrastructure)

### Phase 4: Remote-Only Execution

- [ ] Update `buildbuddy.yaml` format check to auto-commit fixes back to the branch
- [ ] Update CLAUDE.md "Essential Commands" section — remove local `bazel build/test` references
- [ ] Update `.claude/skills/bazel/SKILL.md` — rewrite for remote-first workflow
- [ ] Update `.claude/settings.json` — remove `Bash(bazelisk:*)` permission, add `Bash(bb query:*)` if needed
- [ ] Add PreToolUse hook to block local `bazel build/test/run` commands (redirect to push + trigger)
- [ ] Verify `bb query` works remotely for common query patterns

### Phase 5: Goose Convergence

- [ ] Update `charts/goose-agent/image/apko.yaml` to copy tools from `homelab-tools` image
- [ ] Remove duplicated tool packages from goose-agent apko config
- [ ] Verify Goose agent has identical tool versions to local dev

---

## Security

No deviations from `architecture/security.md`:

- **OCI image** — Built with apko (non-root uid 65532, minimal base, no shell in final image unless needed)
- **GHCR auth** — Uses existing `GHCR_TOKEN` in BuildBuddy secrets for push; pull is public (homelab repo is public)
- **No secrets in image** — Tools image contains only binaries, no credentials
- **Remote execution** — BuildBuddy auth via `bb login` (existing setup), no credential changes

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| **GHCR outage blocks tool pull** | Low | Medium | Cache `.tools/` locally with 24h TTL. Tools persist across outages. |
| **Format auto-commit race** | Medium | Low | CI format job creates a separate commit. Developer must pull before pushing again. Standard git workflow. |
| **Remote query latency** | Medium | Low | `bb query` adds network round-trip (~1-2s). Acceptable for infrequent queries. BuildBuddy MCP covers common cases. |
| **Tool version drift** | Low | Medium | Single source of truth (apko.yaml). ArgoCD Image Updater pins digests. Version changes are tracked in git. |
| **Docker/Podman not available** | Low | High | Document requirement in README. Most dev machines have one. Fallback: `crane export` if container runtime unavailable. |
| **apko can't package all tools** | Medium | Medium | Some tools (like `bb` itself) may not be in Wolfi repos. Fallback: download binary in a build step and copy into image. |

---

## Open Questions

1. **`format` auto-commit strategy** — Should CI push format fixes directly to the branch, or create a separate fixup PR? Direct push is simpler but may surprise developers who have local uncommitted changes.

2. **Tool staleness check** — The 24h TTL in `.envrc` is simple but coarse. Should we pin to a specific digest in a lockfile (e.g., `.tools.lock`) and only update when the lockfile changes? This would give reproducible tool versions but adds a manual update step.

3. **`bb` packaging** — The BuildBuddy CLI is distributed as a standalone binary, not a Wolfi package. How should it be included in the apko image — download in a pre-build step, or maintain a local apko package?

4. **Transition period** — Should we support both `bazel_env` and OCI tools during migration, or cut over atomically? Parallel support avoids breakage but doubles maintenance.

5. **Claude Code in-cluster auth** — Claude Code in the tools image enables in-cluster agents to use it directly (potentially replacing Goose). Auth would use `claude setup-token` with the existing `CLAUDE_AUTH_TOKEN` from the `OnePasswordItem`. Should in-cluster Claude Code use the existing LiteLLM proxy, or authenticate directly to Anthropic?

6. **Claude Code version pinning** — Claude Code releases frequently. Should the tools image pin to a specific version (e.g., `@anthropic-ai/claude-code@1.x.y`), or track latest? Pinning avoids surprises but requires manual bumps. ArgoCD Image Updater can't help here since it's an npm package, not an image tag.

---

## References

| Resource | Relevance |
| -------- | --------- |
| [BuildBuddy CLI](https://www.buildbuddy.io/docs/cli/) | `bb` CLI for remote query and execution |
| [apko](https://github.com/chainguard-dev/apko) | OCI image build tool used throughout the repo |
| [rules_apko](https://github.com/chainguard-dev/rules_apko) | Bazel rules for apko image builds |
| [`tools/BUILD` bazel_env rule](../../tools/BUILD) | Current tool distribution mechanism being replaced |
| [BuildBuddy Workflows](https://www.buildbuddy.io/docs/workflows-setup/) | CI pipeline definition in `buildbuddy.yaml` |
| [architecture/security.md](../../security.md) | Cluster security model (this ADR is fully compliant) |

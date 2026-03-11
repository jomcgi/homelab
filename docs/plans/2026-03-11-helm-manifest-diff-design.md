# Helm Manifest Diff for PRs

## Problem

When a PR modifies Helm charts, values files, or chart dependencies, reviewers
have no visibility into what Kubernetes manifests actually change. They must
mentally trace value overrides through templates — error-prone and slow.

## Solution

A BuildBuddy CI action that renders every ArgoCD application's manifests from
both `origin/main` and the PR branch, diffs them with `dyff`, and posts a
self-updating PR comment with collapsible sections per changed app.

## Components

### 1. `bazel/helm/ci-diff-manifests.sh`

Shell script that:

1. **Discovers apps** — finds all `projects/**/deploy/application.yaml` files
2. **Parses each** — extracts `spec.source.path` (chart), `spec.source.helm.releaseName`,
   `spec.destination.namespace`, and `spec.source.helm.valueFiles[]`
3. **Renders from main** — uses `git show origin/main:<file>` to reconstruct
   chart + values into a temp directory, runs `helm template`
4. **Renders from PR** — runs `helm template` on the working tree
5. **Diffs** — `dyff between` each pair of rendered manifests
6. **Posts comment** — collapsible markdown per changed app, self-updating
   via hidden HTML marker and `gh pr comment`

Tools (`helm`, `dyff`, `gh`) are built once via `bazel build @multitool//tools/{helm,dyff,gh}`.

### 2. BuildBuddy CI action in `buildbuddy.yaml`

```yaml
- name: "Manifest diff"
  container_image: "ubuntu-24.04"
  max_retries: 1
  resource_requests:
    disk: "20GB"
  triggers:
    pull_request:
      branches:
        - "*"
      merge_with_base: false
  steps:
    - run: ./bazel/helm/ci-diff-manifests.sh
```

- PR-only (no main pushes)
- No `depends_on` — runs in parallel with other actions
- Non-blocking — exits 0 regardless of diff results
- Runs for all commits including bot commits (image updater, format bot)

### 3. `dyff` in `rules_multitool`

Add to `tools.lock.json` with binaries for linux-amd64, linux-arm64, darwin-arm64.
Register `multitool.dyff.*` repos in `MODULE.bazel`.

### 4. Application discovery

All apps use Helm (no kustomize-only apps). Every `application.yaml` has
`spec.source.helm`. Values files are resolved relative to the chart path
(ArgoCD convention).

### PR comment format

```markdown
## Helm Manifest Diff

3 of 24 applications have manifest changes.

<details>
<summary><code>grimoire</code> — 2 changes</summary>

(dyff output here)

</details>
```

Uses a hidden HTML marker (`<!-- helm-manifest-diff -->`) to find and replace
the comment on subsequent pushes.

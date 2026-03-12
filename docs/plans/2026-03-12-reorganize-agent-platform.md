# Reorganize Agent Platform — Move Standalone Services Out

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move independently-deployed services out of `projects/agent_platform/` into their own top-level `projects/` folders, rename api_gateway → nginx, and delete the unused vllm chart.

**Architecture:** The agent_platform directory currently mixes umbrella chart subcharts (orchestrator, mcp-servers, sandboxes, nats) with standalone ArgoCD applications (api_gateway, cluster_agents, llama_cpp) and dead code (vllm). This reorganization separates concerns so each independently-deployed service lives in its own `projects/` folder, matching the pattern used by every other service in the repo.

**Tech Stack:** Kustomize, ArgoCD Applications, Helm charts, Bazel BUILD files, Go (for cluster_agents)

---

## Important Notes

- `home-cluster/kustomization.yaml` is **auto-generated** by `bazel/images/generate-home-cluster.sh` — don't edit it directly; run `format` to regenerate.
- `agent_platform/kustomization.yaml` is the aggregator that includes the standalone apps — it needs updating.
- `cluster_agents` has a Go binary with a container image at `ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents` — the image repository path changes with the move.
- `api_gateway` and `llama_cpp` use upstream images (nginx, llama-cpp) so their moves only affect deploy paths.
- ArgoCD Application `spec.source.path` must match the new directory location.
- The `bazel/images/BUILD` `push_all` multirun target references `//projects/agent_platform/cluster_agents:image.push`.
- After all moves, run `format` to regenerate BUILD files and `home-cluster/kustomization.yaml`.

---

### Task 1: Delete vllm (unused chart)

**Files:**

- Delete: `projects/agent_platform/vllm/` (entire directory)

**Step 1: Delete the vllm directory**

```bash
rm -rf projects/agent_platform/vllm/
```

**Step 2: Verify no remaining references**

```bash
grep -r "vllm" projects/ --include="*.yaml" --include="*.bzl" --include="BUILD" -l
```

Expected: No results (vllm was never wired into kustomization.yaml or any ArgoCD app).

**Step 3: Commit**

```bash
git add -A projects/agent_platform/vllm/
git commit -m "chore(agent-platform): remove unused vllm chart"
```

---

### Task 2: Move api_gateway → projects/nginx/

**Files:**

- Move: `projects/agent_platform/api_gateway/` → `projects/nginx/`
- Modify: `projects/nginx/deploy/application.yaml` (update source path)
- Modify: `projects/agent_platform/kustomization.yaml` (remove api_gateway reference)

**Step 1: Move the directory**

```bash
mkdir -p projects/nginx
mv projects/agent_platform/api_gateway/deploy projects/nginx/deploy
mv projects/agent_platform/api_gateway/README.md projects/nginx/README.md
rmdir projects/agent_platform/api_gateway
```

**Step 2: Update ArgoCD Application source path**

In `projects/nginx/deploy/application.yaml`, change:

```yaml
path: projects/agent_platform/api_gateway/deploy
```

to:

```yaml
path: projects/nginx/deploy
```

All other fields (`metadata.name: api-gateway`, `namespace: api-gateway`, `releaseName: api-gateway`) stay as-is — they're logical names, not tied to the folder.

**Step 3: Remove from agent_platform kustomization**

In `projects/agent_platform/kustomization.yaml`, remove:

```yaml
- ./api_gateway/deploy
```

**Step 4: Run format to regenerate home-cluster kustomization and BUILD files**

```bash
format
```

Verify `projects/home-cluster/kustomization.yaml` now includes `../../projects/nginx/deploy` (as a standalone) and no longer has `api_gateway` nested under the agent_platform aggregator.

**Step 5: Render Helm template to verify chart still works**

```bash
helm template api-gateway projects/nginx/deploy/ -f projects/nginx/deploy/values.yaml
```

Expected: Renders successfully with nginx deployment, service, configmap, etc.

**Step 6: Commit**

```bash
git add -A projects/agent_platform/api_gateway/ projects/nginx/ projects/agent_platform/kustomization.yaml
git commit -m "refactor: move api_gateway to projects/nginx"
```

---

### Task 3: Move llama_cpp → projects/llama_cpp/

**Files:**

- Move: `projects/agent_platform/llama_cpp/` → `projects/llama_cpp/`
- Modify: `projects/llama_cpp/deploy/application.yaml` (update source path)
- Modify: `projects/agent_platform/kustomization.yaml` (remove llama_cpp reference)

**Step 1: Move the directory**

```bash
mv projects/agent_platform/llama_cpp projects/llama_cpp
```

**Step 2: Update ArgoCD Application source path**

In `projects/llama_cpp/deploy/application.yaml`, change:

```yaml
path: projects/agent_platform/llama_cpp/deploy
```

to:

```yaml
path: projects/llama_cpp/deploy
```

**Step 3: Remove from agent_platform kustomization**

In `projects/agent_platform/kustomization.yaml`, remove:

```yaml
- ./llama_cpp/deploy
```

**Step 4: Run format**

```bash
format
```

Verify `projects/home-cluster/kustomization.yaml` now includes `../../projects/llama_cpp/deploy`.

**Step 5: Render Helm template to verify**

```bash
helm template llama-cpp projects/llama_cpp/deploy/ -f projects/llama_cpp/deploy/values.yaml
```

Expected: Renders successfully.

**Step 6: Commit**

```bash
git add -A projects/agent_platform/llama_cpp/ projects/llama_cpp/ projects/agent_platform/kustomization.yaml
git commit -m "refactor: move llama_cpp out of agent_platform"
```

---

### Task 4: Move cluster_agents → projects/cluster_agents/

This is the most involved move because cluster_agents has Go source code, a container image, and an image updater config — all with paths that reference `agent_platform/cluster_agents`.

**Files:**

- Move: `projects/agent_platform/cluster_agents/` → `projects/cluster_agents/`
- Modify: `projects/cluster_agents/deploy/application.yaml` (update source path)
- Modify: `projects/cluster_agents/BUILD` (update importpath + image repository)
- Modify: `projects/cluster_agents/deploy/values.yaml` (update image repository)
- Modify: `projects/cluster_agents/deploy/values-prod.yaml` (update image repository)
- Modify: `projects/cluster_agents/deploy/imageupdater.yaml` (update image name)
- Modify: `projects/agent_platform/kustomization.yaml` (remove cluster_agents reference)
- Modify: `bazel/images/BUILD` (update push_all target path)

**Step 1: Move the directory**

```bash
mv projects/agent_platform/cluster_agents projects/cluster_agents
```

**Step 2: Update ArgoCD Application source path**

In `projects/cluster_agents/deploy/application.yaml`, change:

```yaml
path: projects/agent_platform/cluster_agents/deploy
```

to:

```yaml
path: projects/cluster_agents/deploy
```

**Step 3: Update Go BUILD file**

In `projects/cluster_agents/BUILD`, update:

```starlark
# importpath change
importpath = "github.com/jomcgi/homelab/projects/agent_platform/cluster_agents",
```

to:

```starlark
importpath = "github.com/jomcgi/homelab/projects/cluster_agents",
```

And update the image repository:

```starlark
repository = "ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents",
```

to:

```starlark
repository = "ghcr.io/jomcgi/homelab/projects/cluster_agents",
```

**Step 4: Update container image references in deploy values**

In `projects/cluster_agents/deploy/values.yaml`, change:

```yaml
repository: ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents
```

to:

```yaml
repository: ghcr.io/jomcgi/homelab/projects/cluster_agents
```

In `projects/cluster_agents/deploy/values-prod.yaml`, change:

```yaml
repository: ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents
```

to:

```yaml
repository: ghcr.io/jomcgi/homelab/projects/cluster_agents
```

**Step 5: Update image updater config**

In `projects/cluster_agents/deploy/imageupdater.yaml`, change:

```yaml
imageName: ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents:main
```

to:

```yaml
imageName: ghcr.io/jomcgi/homelab/projects/cluster_agents:main
```

**Step 6: Update bazel/images/BUILD push_all target**

In `bazel/images/BUILD`, change:

```starlark
        "//projects/agent_platform/cluster_agents:image.push",
```

to:

```starlark
        "//projects/cluster_agents:image.push",
```

**Step 7: Remove from agent_platform kustomization**

In `projects/agent_platform/kustomization.yaml`, remove:

```yaml
- ./cluster_agents/deploy
```

At this point the kustomization should only contain:

```yaml
resources:
  - ./deploy
```

**Step 8: Run format**

```bash
format
```

This regenerates BUILD files and `home-cluster/kustomization.yaml`. Verify the generated home-cluster kustomization includes `../../projects/cluster_agents/deploy`.

**Step 9: Render Helm template to verify**

```bash
helm template cluster-agents projects/cluster_agents/deploy/ -f projects/cluster_agents/deploy/values.yaml
```

Expected: Renders successfully with image `ghcr.io/jomcgi/homelab/projects/cluster_agents`.

**Step 10: Commit**

```bash
git add -A projects/agent_platform/cluster_agents/ projects/cluster_agents/ projects/agent_platform/kustomization.yaml bazel/images/BUILD
git commit -m "refactor: move cluster_agents out of agent_platform"
```

---

### Task 5: Verify final state

**Step 1: Check agent_platform kustomization only has the umbrella chart**

`projects/agent_platform/kustomization.yaml` should contain:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ./deploy
```

**Step 2: Check home-cluster kustomization includes all moved services**

```bash
cat projects/home-cluster/kustomization.yaml
```

Should include (among others):

- `../../projects/agent_platform` (umbrella chart only now)
- `../../projects/cluster_agents/deploy`
- `../../projects/llama_cpp/deploy`
- `../../projects/nginx/deploy`

**Step 3: Verify no dangling references to old paths**

```bash
grep -r "agent_platform/api_gateway\|agent_platform/llama_cpp\|agent_platform/cluster_agents\|agent_platform/vllm" projects/ bazel/ --include="*.yaml" --include="*.bzl" --include="BUILD" -l
```

Expected: No results (docs/plans/ references are fine — they're historical).

**Step 4: Push and create PR**

```bash
git push -u origin refactor/reorganize-agent-platform
gh pr create --title "refactor: move standalone services out of agent_platform" --body "$(cat <<'EOF'
## Summary
- Move `api_gateway` → `projects/nginx/` (folder rename, soon to be deprecated)
- Move `llama_cpp` → `projects/llama_cpp/`
- Move `cluster_agents` → `projects/cluster_agents/` (includes image repo path change)
- Delete unused `vllm/` chart
- `agent_platform/` now only contains the umbrella chart and its source code (orchestrator, mcp-servers, sandboxes, goose_agent, buildbuddy_mcp)

## Motivation
The agent_platform directory mixed umbrella chart subcharts with independently-deployed ArgoCD applications. This reorganization gives each standalone service its own `projects/` folder, matching the pattern used by all other services.

## Test plan
- [ ] CI passes (format check + bazel test)
- [ ] ArgoCD syncs all four apps successfully after merge (api-gateway, llama-cpp, cluster-agents, agent-platform umbrella)
- [ ] cluster-agents image builds and pushes to new registry path
- [ ] Image updater picks up the new image path for cluster-agents

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Post-Merge Verification

After merge, verify via MCP tools:

1. `argocd-mcp-get-application` for `api-gateway`, `llama-cpp`, `cluster-agents`, `agent-platform` — all should sync
2. The first CI run on main will push the cluster-agents image to the new `ghcr.io/jomcgi/homelab/projects/cluster_agents` path
3. Image updater will need the new image to exist before it can track it — monitor for a successful digest update

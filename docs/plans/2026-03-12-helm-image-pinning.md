# Helm Image Pinning at Build Time

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge Bazel-generated image pins (repository + tag) directly into the chart's `values.yaml` at build time, so Helm auto-loads them without extra `-f` flags or ArgoCD config.

**Architecture:** The `helm_package` rule currently copies generated image values into a separate `values-generated.yaml` inside the chart `.tgz`. This file is never consumed — Helm only auto-loads `values.yaml`. We vendor `yq` via `rules_multitool` and use it in `_helm_package_impl` to deep-merge the generated values into the chart's `values.yaml` before packaging. No changes needed to ArgoCD Applications or deploy values.

**Tech Stack:** Starlark (Bazel rules), shell (package action), yq v4.52.4 (YAML merge), rules_multitool

---

### Task 1: Vendor yq in rules_multitool

**Files:**

- Modify: `bazel/tools/tools.lock.json` (append `yq` entry at end before closing `}`)
- Modify: `MODULE.bazel:54-96` (add `multitool.yq.*` repos to `use_repo`)

**Step 1: Add yq to tools.lock.json**

Add the following entry after the `"starpls"` block (before the final `}`):

```json
  "yq": {
    "binaries": [
      {
        "kind": "archive",
        "url": "https://github.com/mikefarah/yq/releases/download/v4.52.4/yq_linux_arm64.tar.gz",
        "file": "./yq_linux_arm64",
        "sha256": "10a4a2093090363a00b55ad52e132a082f9652970cb8f1ad35a1ae048b917e6e",
        "os": "linux",
        "cpu": "arm64"
      },
      {
        "kind": "archive",
        "url": "https://github.com/mikefarah/yq/releases/download/v4.52.4/yq_linux_amd64.tar.gz",
        "file": "./yq_linux_amd64",
        "sha256": "3fa3c1c32d94520102ea4d853d03c3ab907867d964540e896410ad8a7fc6c8f7",
        "os": "linux",
        "cpu": "x86_64"
      },
      {
        "kind": "archive",
        "url": "https://github.com/mikefarah/yq/releases/download/v4.52.4/yq_darwin_arm64.tar.gz",
        "file": "./yq_darwin_arm64",
        "sha256": "99778ab9ac307b89889607a8f84b4c16e668077ccb8665617547b9059a219ecc",
        "os": "macos",
        "cpu": "arm64"
      },
      {
        "kind": "archive",
        "url": "https://github.com/mikefarah/yq/releases/download/v4.52.4/yq_darwin_amd64.tar.gz",
        "file": "./yq_darwin_amd64",
        "sha256": "b05d49a6e4dd1897bf3a16e080b249f16ac7c87b7e6ce85253d52f130b671b6a",
        "os": "macos",
        "cpu": "x86_64"
      }
    ]
  }
```

**Step 2: Register yq repos in MODULE.bazel**

Add these lines inside the `use_repo(multitool, ...)` block after the `shfmt` entries:

```starlark
    "multitool.yq.linux_arm64",
    "multitool.yq.linux_x86_64",
    "multitool.yq.macos_arm64",
```

**Step 3: Commit**

```bash
git add bazel/tools/tools.lock.json MODULE.bazel
git commit -m "build: vendor yq v4.52.4 via rules_multitool"
```

---

### Task 2: Update helm_package to merge values overlay into values.yaml

**Files:**

- Modify: `bazel/helm/push.bzl:13-86` (`_helm_package_impl`)

**Step 1: Add `_yq` attr to `helm_package` rule**

In the `helm_package` rule attrs (line 91-112), add a `_yq` attr:

```starlark
        "_yq": attr.label(
            default = "@multitool//tools/yq",
            executable = True,
            cfg = "exec",
        ),
```

And add `ctx.executable._yq` to the `tools` list in `run_shell` (line 55).

**Step 2: Replace values_overlay_copy with yq merge**

In `_helm_package_impl` (around line 44-50), change the `values_overlay_copy` logic from:

```python
    values_overlay_copy = ""
    extra_inputs = list(ctx.files.srcs)
    if ctx.file.values_overlay:
        values_overlay_copy = "cp \"{src}\" \"$WORK_DIR/values-generated.yaml\"".format(
            src = ctx.file.values_overlay.path,
        )
        extra_inputs.append(ctx.file.values_overlay)
```

to:

```python
    values_overlay_merge = ""
    extra_inputs = list(ctx.files.srcs)
    if ctx.file.values_overlay:
        values_overlay_merge = (
            "\"{yq}\" eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' " +
            "\"$WORK_DIR/values.yaml\" \"{overlay}\" > \"$WORK_DIR/values.yaml.tmp\"\n" +
            "mv \"$WORK_DIR/values.yaml.tmp\" \"$WORK_DIR/values.yaml\""
        ).format(
            yq = ctx.executable._yq.path,
            overlay = ctx.file.values_overlay.path,
        )
        extra_inputs.append(ctx.file.values_overlay)
```

Update the shell command format substitution from `{values_overlay_copy}` to `{values_overlay_merge}`.

**Step 3: Update the doc comment on `values_overlay` attr**

Change the doc from mentioning `values-generated.yaml` to:

```starlark
            doc = "Optional generated values file to deep-merge into the chart's "
                  "values.yaml before packaging (e.g. the output of helm_images_values).",
```

**Step 4: Run the existing helm lint test to verify**

```bash
bazel test //projects/agent_platform/chart:lint_test
```

Expected: PASS (lint test already passes generated values via `-f`; after merge they're in `values.yaml` directly)

**Step 5: Commit**

```bash
git add bazel/helm/push.bzl
git commit -m "fix(helm): merge image pins into values.yaml at build time

Previously, generated image values were stored as a separate
values-generated.yaml that Helm never auto-loaded. Now yq
deep-merges them into the chart's values.yaml before packaging,
so pinned image tags are used by default without extra -f flags."
```

---

### Task 3: Update helm_lint_test to not double-pass image values

**Files:**

- Modify: `bazel/helm/chart.bzl:60-65`

**Step 1: Remove extra_values from lint test**

Since image values are now merged into `values.yaml`, passing them again via `-f` is redundant. In `chart.bzl`, change:

```python
    if lint:
        helm_lint_test(
            name = "lint_test",
            extra_values = [images_values_target] if images_values_target else [],
            tags = ["chart", "lint"],
        )
```

to:

```python
    if lint:
        helm_lint_test(
            name = "lint_test",
            tags = ["chart", "lint"],
        )
```

**Step 2: Run lint test to verify**

```bash
bazel test //projects/agent_platform/chart:lint_test
```

Expected: PASS

**Step 3: Commit**

```bash
git add bazel/helm/chart.bzl
git commit -m "refactor(helm): remove redundant extra_values from lint test

Image values are now merged into values.yaml at package time,
so passing them separately to helm lint is no longer needed."
```

---

### Task 4: Clean up references to values-generated.yaml

**Files:**

- Modify: `bazel/helm/push.bzl` (update comment on line 42-43)
- Modify: `bazel/helm/chart.bzl` (update docstring around line 25-36)

**Step 1: Update comments**

In `push.bzl`, update the comment near the `values_overlay` attr doc (already done in Task 2).

In `chart.bzl`, update the `helm_chart` docstring to reflect that images are merged into `values.yaml`:

Change:

```
                Produces (in bazel-out):
                    image:
                      repository: ghcr.io/jomcgi/homelab/projects/todo_app/image
                      tag: main-abc1234
```

to:

```
                At build time the generated values are deep-merged into the
                chart's values.yaml, overriding the default repository and tag
                for each image path.
```

**Step 2: Commit**

```bash
git add bazel/helm/push.bzl bazel/helm/chart.bzl
git commit -m "docs(helm): update comments for values merge approach"
```

---

### Task 5: Verify end-to-end with helm template

**Step 1: Render the agent-platform chart and check image tags**

```bash
bazel run //projects/agent_platform/chart:chart.package
# Extract and inspect
TMP=$(mktemp -d)
tar -xzf bazel-bin/projects/agent_platform/chart/chart.package.tgz -C "$TMP"
grep -A2 'repository:.*goose_agent' "$TMP"/*/values.yaml
```

Expected: `tag:` should show a pinned value (not `main`).

**Step 2: Full helm template render**

```bash
helm template test "$TMP"/agent-platform/ -f projects/agent_platform/deploy/values.yaml | grep 'image:.*goose_agent'
```

Expected: Image reference should include the pinned tag.

**Step 3: Clean up and push**

```bash
rm -rf "$TMP"
git push origin fix/helm-image-pinning
```

Create PR:

```bash
gh pr create --title "fix(helm): merge image pins into chart values.yaml at build time" --body "$(cat <<'EOF'
## Summary
- Vendors yq v4.52.4 via rules_multitool
- Changes `helm_package` to deep-merge generated image values into `values.yaml` instead of creating an unused `values-generated.yaml`
- Fixes goose sandbox pods using unpinned `:main` tag instead of CI-built digests

## Context
The `helm_images_values` rule generates pinned image references, but they were stored as `values-generated.yaml` — a file Helm never auto-loads. ArgoCD's `application.yaml` only references the deploy `values.yaml`, so the pins were silently ignored. Sandbox pods fell back to `tag: main` from chart defaults.

## Test plan
- [ ] `bazel test //projects/agent_platform/chart:lint_test` passes
- [ ] Extracted chart `.tgz` shows pinned tags in `values.yaml`
- [ ] `helm template` renders pinned image references
- [ ] CI passes (BuildBuddy)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

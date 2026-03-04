# Fix py3_image source file packaging — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `py3_image` macro to automatically include the main `.py` source file that `py_venv_binary` omits from runfiles.

**Architecture:** Add a supplementary tar layer containing the main source file at the correct runfiles path. Auto-derive the filename from the binary name for same-package targets; skip cross-package targets (their sources already exist in transitive deps).

**Tech Stack:** Starlark (Bazel), `@aspect_bazel_lib//lib:tar.bzl` (inline mtree), `@rules_oci`

---

### Task 1: Add `tar` import to `py3_image.bzl`

**Files:**
- Modify: `tools/oci/py3_image.bzl:1-7` (imports)

**Step 1: Add the import**

Add the `tar` rule import alongside existing loads:

```python
load("@aspect_bazel_lib//lib:tar.bzl", "tar")
```

Place it after the existing `expand_template` import (line 3), before `transitions`.

**Step 2: Verify file still parses**

Run: `bb build --nobuild //tools/oci:py3_image`
Expected: Build succeeds (just loads the bzl file, no analysis)

**Step 3: Commit**

```bash
git add tools/oci/py3_image.bzl
git commit -m "build(oci): add tar import to py3_image.bzl"
```

---

### Task 2: Add `main` parameter and source tar creation

**Files:**
- Modify: `tools/oci/py3_image.bzl:9-30` (function signature and path computation)

**Step 1: Add `main` parameter to function signature**

Change the function signature from:

```python
def py3_image(name, binary, root = "/", layer_groups = {}, env = {}, workdir = None, base = "@python_base", repository = None, visibility = ["//images:__pkg__"], multi_platform = True):
```

To:

```python
def py3_image(name, binary, main = None, root = "/", layer_groups = {}, env = {}, workdir = None, base = "@python_base", repository = None, visibility = ["//images:__pkg__"], multi_platform = True):
```

Add docstring entry for `main`:

```
        main: The main .py source file for the binary. Auto-derived as "{binary_name}.py"
              for same-package binaries. Set explicitly for non-standard naming. Cross-package
              binaries are skipped (their sources are in transitive deps).
```

**Step 2: Add auto-derive logic and tar creation**

After the `env` dict computation (after line 35), add:

```python
    # py_venv_binary omits ctx.file.main from runfiles — create a supplementary
    # tar layer to include the source file at the correct runfiles path.
    src_tars = []
    if main == None and binary.package == native.package_name():
        main = binary.name + ".py"
    if main:
        main_label = str(binary).rsplit(":", 1)[0] + ":" + main
        source_dest = ".{}/{}/{}".format(workspace_root, binary.package, main)
        tar(
            name = name + "_srcs",
            srcs = [main_label],
            mtree = [
                "{} type=file content=$(execpath {})".format(source_dest, main_label),
            ],
        )
        src_tars = [name + "_srcs"]
```

**Step 3: Append `src_tars` to all `oci_image` tars lists**

In the `multi_platform = True` branch, change both `oci_image` calls:

AMD64 (around line 42):
```python
            tars = py_image_layer(
                name = name + "_layers_amd64",
                binary = binary,
                root = root,
                layer_groups = layer_groups,
            ) + src_tars,
```

ARM64 (around line 62):
```python
            tars = py_image_layer(
                name = name + "_layers_arm64",
                binary = binary,
                root = root,
                layer_groups = layer_groups,
            ) + src_tars,
```

In the `else` (single platform) branch (around line 106):
```python
            tars = py_image_layer(
                name = name + "_layers",
                binary = binary,
                root = root,
                layer_groups = layer_groups,
            ) + src_tars,
```

**Step 4: Verify syntax**

Run: `bb build --nobuild //tools/oci:py3_image`
Expected: succeeds

**Step 5: Commit**

```bash
git add tools/oci/py3_image.bzl
git commit -m "feat(oci): auto-include py_venv_binary main source in py3_image"
```

---

### Task 3: Update `tools/oci/BUILD` deps

**Files:**
- Modify: `tools/oci/BUILD:31-41` (py3_image bzl_library)

**Step 1: Add `tar` dependency**

Add `"@aspect_bazel_lib//lib:tar"` to the `py3_image` bzl_library deps:

```python
bzl_library(
    name = "py3_image",
    srcs = ["py3_image.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_bazel_lib//lib:tar",
        "@aspect_bazel_lib//lib:transitions",
        "@aspect_rules_py//py:defs",
        "@rules_oci//oci:defs",
        "@rules_shell//shell:rules_bzl",
    ],
)
```

**Step 2: Commit**

```bash
git add tools/oci/BUILD
git commit -m "build(oci): add tar dep to py3_image bzl_library"
```

---

### Task 4: Build affected images to verify fix

**Step 1: Build all four broken images**

Run: `bb build //services/hikes/update_forecast:update_image //services/ships_api:image //services/ais_ingest:image //services/trips_api:image`

Expected: BUILD SUCCESS — all four images build without errors.

**Step 2: Run existing config tests**

Run: `bb test //services/hikes/update_forecast:update_image_config_test //services/ships_api:image_config_test //services/ais_ingest:image_config_test //services/trips_api:image_config_test`

Expected: All 4 PASSED.

**Step 3: Verify source file is present in image**

Pick one image (hikes/update_forecast) and inspect:

```bash
bb build //services/hikes/update_forecast:update_image_base_amd64
# Find the _srcs tar and list its contents:
bb build //services/hikes/update_forecast:update_image_srcs
tar tf bazel-bin/services/hikes/update_forecast/update_image_srcs.tar
```

Expected: tar contains `services/hikes/update_forecast/update.runfiles/_main/services/hikes/update_forecast/update.py`

**Step 4: Verify already-working images still build**

Run: `bb build //services/stargazer/app:image //services/buildbuddy_mcp/app:image //services/knowledge_graph/app:image`

Expected: BUILD SUCCESS — cross-package images unaffected (no `_srcs` tar created for them).

**Step 5: Commit nothing (verification only)**

No changes — this task is just verification.

---

### Task 5: Run full test suite

**Step 1: Run all tests**

Run: `bb test //...`

Expected: All tests pass. No regressions.

---

### Task 6: Push and create PR

**Step 1: Push branch**

```bash
git push -u origin fix/py3-image-venv-srcs
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "fix(oci): include py_venv_binary main source in py3_image" \
  --body "$(cat <<'EOF'
## Summary

- `py_venv_binary` omits `ctx.file.main` from runfiles, causing the source `.py`
  file to be missing from container images built with `py3_image`
- Adds a supplementary tar layer containing the main source file at the correct
  runfiles path (`{workspace_root}/{package}/{main}.py`)
- Auto-derives the filename from the binary name for same-package targets;
  cross-package targets are skipped (sources already in transitive deps)

**Fixes:** ships_api, ais_ingest, trips_api, hikes/update_forecast

**No BUILD file changes required** — all broken services follow `{name}.py` convention.

## Test plan

- [ ] All four broken images build successfully
- [ ] Existing `_config_test` tests pass for all images
- [ ] Source `.py` file present in `_srcs` tar at correct runfiles path
- [ ] Already-working images (stargazer, buildbuddy_mcp, knowledge_graph) unaffected
- [ ] Full `bazel test //...` passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

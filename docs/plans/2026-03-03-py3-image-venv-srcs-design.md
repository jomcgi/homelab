# Fix py3_image source file packaging for py_venv_binary

## Problem

`py_venv_binary` from `aspect_rules_py` does not include `ctx.file.main` (the entry
point `.py` file) in its runfiles. When `py_image_layer` packages the binary's runfiles
into container layers, the source file is missing from the image.

The launcher script references the main file via `rlocation`, but since the file isn't
in the runfiles, it doesn't exist in the container. Python fails with:

```
can't find '__main__' module in '<workspace_root>'
```

This affects all `py_venv_binary` targets where the main file is not also present in a
transitive dependency's `srcs`. Broken: ships_api, ais_ingest, trips_api,
hikes/update_forecast. Unaffected (main in transitive dep): buildbuddy_mcp, stargazer,
knowledge_graph.

## Solution

Add a supplementary tar layer to `py3_image` containing the main `.py` file at the
correct runfiles path.

### API change

```python
def py3_image(name, binary, main = None, ...):
```

- `main = None` — auto-derive as `"{binary.name}.py"` for same-package binaries.
  Cross-package binaries are skipped (their sources are in transitive deps).
- `main = "custom.py"` — explicit override for non-standard naming.

### Mechanism

1. Resolve `main` file label from binary name convention
2. Use `mtree_spec` + `mtree_mutate` + `tar` to create a small tar placing the file at
   `{workspace_root}/{binary.package}/{main_filename}`
3. Append this tar to `oci_image` tars alongside `py_image_layer` output

### Path computation

```
workspace_root = {root}{binary.package}/{binary.name}.runfiles/_main
source_dest    = {workspace_root}/{binary.package}/{main_filename}
```

### Scope

This fixes the missing source file. The empty `_aspect.pth` in containers is an
upstream aspect_rules_py bug, already mitigated by `PYTHONPATH` env var (commit
35b79d84).

### Zero BUILD changes required

All broken services follow the `{name}.py` convention. Auto-derivation handles them.

load("@bazel_skylib//:bzl_library.bzl", "bzl_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")

# gazelle:exclude python_deps.py

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load(":multitool_tar.bzl", "multitool_tar")
load(":node_tar.bzl", "node_tar")
load(":python_tar.bzl", "python_tar")

multitool_tar(
    name = "tools_tar",
    tools = [
        "argocd",
        "buildozer",
        "crane",
        "gazelle",
        "gh",
        "gofumpt",
        "helm",
        "kind",
        "op",
        "ruff",
        "shfmt",
    ],
)

# Per-platform Node.js binary tars.
# Creates :node_tar_linux_amd64, :node_tar_linux_arm64, :node_tar_darwin_arm64
# each containing /usr/bin/node for the target platform.
node_tar(name = "node_tar")

# Package pnpm from the aspect_rules_js-managed @pnpm repo.
# pnpm is a JS script (cross-platform) that runs on Node.js.
# Places the package at /usr/local/lib/node_modules/pnpm/
# with a symlink at /usr/bin/pnpm for PATH discovery.
# nosemgrep: single-npm-package-in-apko-genrule -- pnpm is self-contained, not a single JS module
genrule(
    name = "pnpm_tar",
    srcs = ["@pnpm//:pkg"],
    outs = ["pnpm.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/pnpm"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(location @pnpm//:pkg)' | tr ' ' '\\n' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/bin/pnpm.cjs"
        mkdir -p "$$WORK/usr/bin"
        ln -s "../local/lib/node_modules/pnpm/bin/pnpm.cjs" "$$WORK/usr/bin/pnpm"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Package prettier from the pnpm lockfile-managed npm package.
# Places the package at /usr/local/lib/node_modules/prettier/
# with a symlink at /usr/bin/prettier for PATH discovery.
genrule(
    name = "prettier_tar",
    srcs = ["//:node_modules/prettier"],
    outs = ["prettier.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/prettier"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(locations //:node_modules/prettier)' | tr ' ' '\\n' | grep 'prettier$$' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/bin/prettier.cjs"
        mkdir -p "$$WORK/usr/bin"
        ln -s "../local/lib/node_modules/prettier/bin/prettier.cjs" "$$WORK/usr/bin/prettier"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Package the homelab CLI into the tools image.
# Source files go into the python_deps runfiles tree so they're importable
# via the shared Python runtime (tools.cli.main). A wrapper script at
# /usr/bin/homelab execs the module.
genrule(
    name = "homelab_cli_tar",
    srcs = [
        "//tools:__init__.py",
        "//tools/cli:__init__.py",
        "//tools/cli:auth.py",
        "//tools/cli:knowledge_cmd.py",
        "//tools/cli:main.py",
        "//tools/cli:output.py",
    ],
    outs = ["homelab_cli.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        # Place source files in the python_deps runfiles workspace root
        # so `from tools.cli.main import app` resolves naturally.
        DEST="$$WORK/bazel/tools/image/python_deps.runfiles/_main"
        mkdir -p "$$DEST/tools/cli"
        cp $(location //tools:__init__.py) "$$DEST/tools/__init__.py"
        cp $(location //tools/cli:__init__.py) "$$DEST/tools/cli/__init__.py"
        cp $(location //tools/cli:auth.py) "$$DEST/tools/cli/auth.py"
        cp $(location //tools/cli:knowledge_cmd.py) "$$DEST/tools/cli/knowledge_cmd.py"
        cp $(location //tools/cli:main.py) "$$DEST/tools/cli/main.py"
        cp $(location //tools/cli:output.py) "$$DEST/tools/cli/output.py"
        # Wrapper script
        mkdir -p "$$WORK/usr/bin"
        cat > "$$WORK/usr/bin/homelab" << 'WRAPPER'
#!/usr/bin/env bash
exec python3 -m tools.cli.main "$$@"
WRAPPER
        chmod 755 "$$WORK/usr/bin/homelab"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Shim py_venv_binary that declares all monorepo pip deps.
# The binary itself does nothing — it exists solely so py_image_layer can
# package its transitive dependency tree (interpreter + stdlib + pip packages).
# Platform-conditional packages (e.g. pyobjc on macOS, dbus_fast on Linux)
# are handled by rules_python's platform-aware wheel resolution.
py_venv_binary(
    name = "python_deps",
    main = "python_deps.py",
    deps = [  # keep
        "@pip//httpx",  # keep
        "@pip//typer",  # keep
    ],
)

# Per-platform Python runtime + pip deps tars.
# Creates :python_tar_linux_amd64, :python_tar_linux_arm64, :python_tar_darwin_arm64
# each containing py_image_layer tars (interpreter + stdlib + pip packages)
# for the target platform.
#
# NOTE: darwin_arm64 is experimental — py_image_layer was designed for Linux
# OCI container images and may not produce valid tars for macOS. If the
# darwin variant fails to build, the Linux variants are still usable.
python_tar(
    name = "python_tar",
    binary = ":python_deps",
)

oci_image(
    name = "image_linux_amd64",
    architecture = "amd64",
    os = "linux",
    tars = [
        ":tools_tar_linux_amd64",
        ":node_tar_linux_amd64",
        ":python_tar_linux_amd64",
        ":pnpm_tar",
        ":prettier_tar",
        ":homelab_cli_tar",
    ],
)

oci_image(
    name = "image_linux_arm64",
    architecture = "arm64",
    os = "linux",
    tars = [
        ":tools_tar_linux_arm64",
        ":node_tar_linux_arm64",
        ":python_tar_linux_arm64",
        ":pnpm_tar",
        ":prettier_tar",
        ":homelab_cli_tar",
    ],
)

oci_image(
    name = "image_darwin_arm64",
    architecture = "arm64",
    os = "darwin",
    tars = [
        ":tools_tar_darwin_arm64",
        ":node_tar_darwin_arm64",
        ":python_tar_darwin_arm64",
        ":pnpm_tar",
        ":prettier_tar",
        ":homelab_cli_tar",
    ],
)

oci_image_index(
    name = "image",
    images = [
        ":image_linux_amd64",
        ":image_linux_arm64",
        ":image_darwin_arm64",
    ],
)

# Stamped tags for CI (branch + timestamp)
expand_template(
    name = "image_stamped_tags_ci",
    out = "image_stamped_ci.tags.txt",
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = [
        "{STABLE_BRANCH_TAG}",
        "{STABLE_IMAGE_TAG}",
    ],
)

# Stamped tags for local builds (timestamp only)
expand_template(
    name = "image_stamped_tags_local",
    out = "image_stamped_local.tags.txt",
    stamp_substitutions = {
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = ["{STABLE_IMAGE_TAG}"],
)

oci_push(
    name = "image.push",
    image = ":image",
    remote_tags = select({
        "//bazel/tools/oci:ci_build": "image_stamped_tags_ci",
        "//conditions:default": "image_stamped_tags_local",
    }),
    repository = "ghcr.io/jomcgi/homelab/bazel/tools/image",
    visibility = ["//bazel/images:__pkg__"],
)

semgrep_target_test(
    name = "python_deps_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":python_deps",
)

bzl_library(
    name = "multitool_tar",
    srcs = ["multitool_tar.bzl"],
    visibility = ["//visibility:public"],
)

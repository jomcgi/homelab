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

# Shim py_venv_binary that declares all monorepo pip deps.
# The binary itself does nothing — it exists solely so py_image_layer can
# package its transitive dependency tree (interpreter + stdlib + pip packages).
# Platform-conditional packages (e.g. pyobjc on macOS, dbus_fast on Linux)
# are handled by rules_python's platform-aware wheel resolution.
py_venv_binary(
    name = "python_deps",
    main = "python_deps.py",
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
    visibility = ["//bazel/images:__pkg__"],
)

semgrep_target_test(
    name = "python_deps_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":python_deps",
)

bzl_library(
    name = "multitool_tar",
    srcs = ["multitool_tar.bzl"],
    visibility = ["//visibility:public"],
)

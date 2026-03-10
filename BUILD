load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

"""Targets in the repository root"""

load("@aspect_rules_js//js:defs.bzl", "js_library")

# We prefer BUILD instead of BUILD.bazel
# gazelle:build_file_name BUILD
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@gazelle//:def.bzl", "gazelle", "gazelle_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
# Python gazelle config moved to //bazel/tools/python to avoid eager-fetching all pip packages during CI analysis

npm_link_all_packages(name = "node_modules")

js_library(
    name = "eslintrc",
    srcs = ["eslint.config.mjs"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":node_modules/@eslint/js",
        ":node_modules/typescript-eslint",
    ],
)

js_library(
    name = "prettierrc",
    srcs = ["prettier.config.cjs"],
    visibility = ["//bazel/tools/format:__pkg__"],
    deps = [],
)

exports_files(
    [
        ".shellcheckrc",
    ],
    visibility = ["//:__subpackages__"],
)

# gazelle:prefix github.com/jomcgi/homelab
# gazelle:exclude .claude

# gazelle:semgrep_target_kinds py_venv_binary

# Custom gazelle binary with ArgoCD and wrangler extensions
gazelle_binary(
    name = "gazelle_binary",
    languages = [
        "//bazel/helm/gazelle",
        "//bazel/wrangler/gazelle",
        "//bazel/semgrep/defs/gazelle",
        "@bazel_skylib_gazelle_plugin//bzl",
        "@gazelle//language/go",
        "@gazelle//language/proto",
        "@rules_python_gazelle_plugin//python",
    ],
)

gazelle(
    name = "gazelle",
    env = {
        "ENABLE_LANGUAGES": ",".join([
            "argocd",
            "wrangler",
            "semgrep",
            "bzl",
            "proto",
            "go",
            "python",
        ]),
    },
    gazelle = ":gazelle_binary",
)

exports_files(
    ["pyproject.toml"],
    visibility = ["//:__subpackages__"],
)

# Produce aspect_rules_py targets rather than rules_python
# gazelle:map_kind py_binary py_venv_binary @aspect_rules_py//py/private/py_venv:defs.bzl
# gazelle:map_kind py_library py_library @aspect_rules_py//py:defs.bzl
# gazelle:map_kind py_test py_test //bazel/tools/pytest:defs.bzl
#
# Don't walk into virtualenvs when looking for python sources.
# We don't intend to plant BUILD files there.
# gazelle:exclude **/*.venv
#
# Python gazelle configuration moved to //bazel/tools/python to avoid eager-fetching
# all pip packages during CI analysis phase. Use:
# - bazel run //bazel/tools/python:gazelle_python_manifest.update
# - bazel test //bazel/tools/python:gazelle_python_manifest.test
#
# Note: gazelle_python.yaml in workspace root is a symlink to bazel/tools/python/gazelle_python.yaml
# because Gazelle expects the manifest file at the workspace root.

py_library(
    name = "homelab",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

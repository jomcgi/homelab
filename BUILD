load("@rules_go//go:def.bzl", "go_test")
load("//rules_semgrep:defs.bzl", "semgrep_test")

"""Targets in the repository root"""

load("@aspect_rules_js//js:defs.bzl", "js_library")

# We prefer BUILD instead of BUILD.bazel
# gazelle:build_file_name BUILD
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@gazelle//:def.bzl", "gazelle", "gazelle_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
# Python gazelle config moved to //tools/python to avoid eager-fetching all pip packages during CI analysis

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
    visibility = ["//tools/format:__pkg__"],
    deps = [],
)

# Code TUI
js_library(
    name = "opencode",
    visibility = ["//visibility:public"],
    deps = [
        ":node_modules/opencode-ai",
    ],
)

exports_files(
    [
        ".shellcheckrc",
    ],
    visibility = ["//:__subpackages__"],
)

# gazelle:prefix github.com/jomcgi/homelab
# gazelle:exclude cdk8s
# gazelle:exclude poc
# gazelle:exclude .claude

# Custom gazelle binary with ArgoCD and wrangler extensions
gazelle_binary(
    name = "gazelle_binary",
    languages = [
        "//rules_helm/gazelle",
        "//rules_wrangler/gazelle",
        "//rules_semgrep/gazelle",
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
# gazelle:map_kind py_test py_test //tools/pytest:defs.bzl
#
# Don't walk into virtualenvs when looking for python sources.
# We don't intend to plant BUILD files there.
# gazelle:exclude **/*.venv
#
# Python gazelle configuration moved to //tools/python to avoid eager-fetching
# all pip packages during CI analysis phase. Use:
# - bazel run //tools/python:gazelle_python_manifest.update
# - bazel test //tools/python:gazelle_python_manifest.test
#
# Note: gazelle_python.yaml in workspace root is a symlink to tools/python/gazelle_python.yaml
# because Gazelle expects the manifest file at the workspace root.

py_library(
    name = "homelab",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

go_test(
    name = "homelab_test",
    srcs = ["deps_test.go"],
    deps = [
        "@com_github_gin_gonic_gin//:gin",
        "@com_github_google_go_containerregistry//pkg/registry",
        "@com_github_google_uuid//:uuid",
        "@com_github_gorilla_websocket//:websocket",
        "@com_github_stretchr_testify//assert",
        "@io_k8s_metrics//pkg/client/clientset/versioned",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

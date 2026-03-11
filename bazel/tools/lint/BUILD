load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

"""Definition of linter tools

This is in its own package because it has so many loading-time symbols,
we don't want to trigger eager fetches of these for builds which aren't running linters.
"""

load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@npm//:eslint/package_json.bzl", eslint_bin = "bin")
load("@rules_go//go:def.bzl", "TOOLS_NOGO", "nogo")

package(default_visibility = ["//:__subpackages__"])

js_library(
    name = "eslintrc",
    srcs = ["eslint.config.mjs"],
    deps = [
        "//:node_modules/@eslint/js",
        "//:node_modules/typescript-eslint",
    ],
)

exports_files(
    [".shellcheckrc"],
)

eslint_bin.eslint_binary(name = "eslint")

nogo(
    name = "nogo",
    visibility = ["//visibility:public"],
    deps = TOOLS_NOGO,
)

bzl_library(
    name = "linters",
    srcs = ["linters.bzl"],
    deps = [
        "@aspect_rules_lint//lint:eslint",
        "@aspect_rules_lint//lint:lint_test",
        "@aspect_rules_lint//lint:ruff",
        "@aspect_rules_lint//lint:shellcheck",
    ],
)

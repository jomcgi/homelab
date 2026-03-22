load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py bazel //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter.rewrite //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter.rewrite.LINK_PATTERN //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter.rewrite.remap_link //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter.rewrite.resolve_link //bazel/vitepress/rewriter:rewriter
# gazelle:resolve py bazel.vitepress.rewriter.rewrite.rewrite_file //bazel/vitepress/rewriter:rewriter

py_venv_binary(
    name = "rewrite",
    srcs = ["rewrite.py"],
    main = "rewrite.py",
    visibility = ["//visibility:public"],
)

py_library(
    name = "rewriter",
    srcs = ["rewrite.py"],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "test_rewrite",
    srcs = ["test_rewrite.py"],
    deps = [
        "//bazel/vitepress/rewriter",
        "@pip//pytest",
    ],
)

semgrep_target_test(
    name = "rewrite_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":rewrite",
)

semgrep_test(
    name = "test_rewrite_semgrep_test",
    srcs = ["test_rewrite.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "knowledge_graph",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "scraper-image",
    binary = "//projects/agent-platform/knowledge-graph/app:scraper",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-scraper",
)

py3_image(
    name = "embedder-image",
    binary = "//projects/agent-platform/knowledge-graph/app:embedder",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-embedder",
)

py3_image(
    name = "mcp-image",
    binary = "//projects/agent-platform/knowledge-graph/app:mcp",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-mcp",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

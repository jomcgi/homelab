load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "blog_knowledge_graph",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "scraper-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:scraper",
    repository = "ghcr.io/jomcgi/homelab/projects/blog_knowledge_graph/scraper",
)

py3_image(
    name = "embedder-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:embedder",
    repository = "ghcr.io/jomcgi/homelab/projects/blog_knowledge_graph/embedder",
)

py3_image(
    name = "mcp-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:mcp",
    repository = "ghcr.io/jomcgi/homelab/projects/blog_knowledge_graph/mcp",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

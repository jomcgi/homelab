load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "knowledge_graph",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "scraper-image",
    binary = "//services/knowledge_graph/app:scraper_main",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-scraper",
)

py3_image(
    name = "embedder-image",
    binary = "//services/knowledge_graph/app:embedder_main",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-embedder",
)

py3_image(
    name = "mcp-image",
    binary = "//services/knowledge_graph/app:mcp_main",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-mcp",
)

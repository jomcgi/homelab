load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py3_image(
    name = "scraper-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:scraper",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-scraper",
)

py3_image(
    name = "embedder-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:embedder",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-embedder",
)

py3_image(
    name = "mcp-image",
    binary = "//projects/blog_knowledge_graph/knowledge_graph/app:mcp",
    repository = "ghcr.io/jomcgi/homelab/services/knowledge-graph-mcp",
)

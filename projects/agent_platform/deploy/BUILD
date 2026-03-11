load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    # Only chart-level images that helm_images_values can resolve (dot-notation).
    # MCP server images use list indexing (servers[N].image) which is unsupported
    # by helm_images_values — those are pinned in the overlay values instead.
    images = {
        "agent-orchestrator.image": "//projects/agent_platform/orchestrator:image.info",
        "goose-sandboxes.sandboxTemplate.image": "//projects/agent_platform/goose_agent/image:image.info",
    },
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

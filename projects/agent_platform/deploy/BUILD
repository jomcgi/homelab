load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "agent-orchestrator.image": "//projects/agent_platform/orchestrator:image.info",
        "goose-sandboxes.sandboxTemplate.image": "//projects/agent_platform/goose_agent/image:image.info",
        "agent-platform-mcp-servers.servers[1].image": "//projects/agent_platform/buildbuddy_mcp:image.info",
        "agent-platform-mcp-servers.servers[4].image": "//projects/todo_app:py_image.info",
        "agent-platform-mcp-servers.servers[5].image": "//projects/agent_platform/orchestrator/mcp:image.info",
    },
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/agent_platform/cluster_agents:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "cluster-agents",
    chart = "projects/agent_platform/cluster_agents/deploy",
    chart_files = ":chart",
    namespace = "cluster-agents",
    release_name = "cluster-agents",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
    ],
)

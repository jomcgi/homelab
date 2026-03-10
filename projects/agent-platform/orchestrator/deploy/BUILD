load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = [":__pkg__"],
)

argocd_app(
    name = "agent-orchestrator",
    chart = "projects/agent-platform/orchestrator/deploy",
    chart_files = ":chart",
    namespace = "agent-orchestrator",
    release_name = "agent-orchestrator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)

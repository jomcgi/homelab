load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = [":__pkg__"],
)

argocd_app(
    name = "api-gateway",
    chart = "projects/agent-platform/api-gateway/deploy",
    chart_files = ":chart",
    namespace = "api-gateway",
    release_name = "api-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)

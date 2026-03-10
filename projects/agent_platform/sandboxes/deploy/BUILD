load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "goose-sandboxes",
    chart = "projects/agent_platform/sandboxes/deploy",
    chart_files = ":chart",
    namespace = "goose-sandboxes",
    release_name = "goose-sandboxes",
    # Agent pods need writable fs for git, npm, build tools
    semgrep_exclude_rules = ["writable-filesystem-container"],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)

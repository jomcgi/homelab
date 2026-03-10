load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = [":__pkg__"],
)

argocd_app(
    name = "context-forge",
    chart = "projects/agent-platform/context-forge/deploy",
    chart_files = ":chart",
    namespace = "mcp-gateway",
    release_name = "context-forge",
    # Upstream mcp-stack chart doesn't expose securityContext
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)

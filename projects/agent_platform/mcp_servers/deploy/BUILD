load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "mcp-servers",
    chart = "projects/agent_platform/mcp_servers/deploy",
    chart_files = ":chart",
    namespace = "mcp-servers",
    release_name = "mcp-servers",
    # Some servers use writableTmp=true by design
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

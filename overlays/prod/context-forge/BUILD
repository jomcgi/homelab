load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "context-forge",
    chart = "charts/context-forge",
    chart_files = "//charts/context-forge:chart",
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
        "//charts/context-forge:values.yaml",
        "values.yaml",
    ],
)

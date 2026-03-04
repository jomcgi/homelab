load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "mcp-servers",
    chart = "charts/mcp-servers",
    chart_files = "//charts/mcp-servers:chart",
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
        "//charts/mcp-servers:values.yaml",
        "values.yaml",
    ],
)

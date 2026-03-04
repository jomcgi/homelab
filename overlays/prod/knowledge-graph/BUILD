load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "knowledge-graph",
    chart = "charts/knowledge-graph",
    chart_files = "//charts/knowledge-graph:chart",
    namespace = "knowledge-graph",
    release_name = "knowledge-graph",
    # Uses aspect_rules_py which needs writable FS and runs as root
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/knowledge-graph:values.yaml",
        "values.yaml",
    ],
)

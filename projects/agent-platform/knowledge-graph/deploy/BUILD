load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = [":__pkg__"],
)

argocd_app(
    name = "knowledge-graph",
    chart = "projects/agent-platform/knowledge-graph/deploy",
    chart_files = ":chart",
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
        "values.yaml",
        "values-prod.yaml",
    ],
)

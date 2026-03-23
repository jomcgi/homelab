load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "knowledge-graph",
    chart = "projects/blog_knowledge_graph/deploy",
    chart_files = ":chart",
    namespace = "knowledge-graph",
    release_name = "knowledge-graph",
    # Uses aspect_rules_py which needs writable FS and runs as root; containers lack readiness probes
    semgrep_exclude_rules = [
        "require-readiness-probe",
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

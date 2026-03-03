load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "longhorn",
    chart = "charts/longhorn",
    chart_files = "//charts/longhorn:chart",
    namespace = "longhorn",
    release_name = "longhorn",
    # Longhorn is a storage system that legitimately requires privileged containers
    semgrep_exclude_rules = ["no-privileged"],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/longhorn:values.yaml",
        "values.yaml",
    ],
)

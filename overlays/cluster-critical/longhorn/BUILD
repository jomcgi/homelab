load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "longhorn",
    chart = "charts/longhorn",
    chart_files = "//charts/longhorn:chart",
    namespace = "longhorn",
    release_name = "longhorn",
    # Longhorn is a storage system that legitimately requires privileged containers
    semgrep_exclude_rules = [
        "no-privileged",
        "yaml.kubernetes.security.privileged-container.privileged-container",
        "yaml.kubernetes.security.allow-privilege-escalation.allow-privilege-escalation",
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/longhorn:values.yaml",
        "values.yaml",
    ],
)

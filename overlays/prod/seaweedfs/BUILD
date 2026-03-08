load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "seaweedfs",
    chart = "charts/seaweedfs",
    chart_files = "//charts/seaweedfs:chart",
    namespace = "seaweedfs",
    release_name = "seaweedfs",
    # Upstream doesn't expose securityContext via wrapper values
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/seaweedfs:values.yaml",
        "values.yaml",
    ],
)

load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "nats",
    chart = "charts/nats",
    chart_files = "//charts/nats:chart",
    namespace = "nats",
    release_name = "nats",
    # Upstream nats chart doesn't expose securityContext
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/nats:values.yaml",
        "values.yaml",
    ],
)

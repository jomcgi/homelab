load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "opentelemetry-operator",
    chart = "charts/opentelemetry-operator",
    chart_files = "//charts/opentelemetry-operator:chart",
    namespace = "opentelemetry-operator",
    release_name = "opentelemetry-operator",
    # Upstream defaults to uid 65532 and runAsNonRoot; only writable FS flagged
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/opentelemetry-operator:values.yaml",
        "values.yaml",
    ],
)

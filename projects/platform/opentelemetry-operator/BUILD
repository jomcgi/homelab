load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "opentelemetry-operator",
    chart = "projects/platform/opentelemetry-operator",
    chart_files = ":chart",
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
        "values.yaml",
        "values-prod.yaml",
    ],
)

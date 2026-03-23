load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "nats",
    chart = "projects/platform/nats",
    chart_files = ":chart",
    namespace = "nats",
    release_name = "nats",
    # Upstream nats chart doesn't expose securityContext; resource limits not configurable for all containers
    semgrep_exclude_rules = [
        "require-resource-limits",
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

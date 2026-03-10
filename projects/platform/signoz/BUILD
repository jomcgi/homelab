load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "signoz",
    chart = "projects/platform/signoz",
    chart_files = ":chart",
    namespace = "signoz",
    release_name = "signoz",
    # Many subcomponents (clickhouse, alertmanager, otel collectors); fixing all via values is fragile
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.allow-privilege-escalation.allow-privilege-escalation",
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

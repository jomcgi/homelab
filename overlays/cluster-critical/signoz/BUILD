load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "signoz",
    chart = "charts/signoz",
    chart_files = "//charts/signoz:chart",
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
        "//charts/signoz:values.yaml",
        "values.yaml",
    ],
)

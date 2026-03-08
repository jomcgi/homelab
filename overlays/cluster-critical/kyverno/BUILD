load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "kyverno",
    chart = "charts/kyverno",
    chart_files = "//charts/kyverno:chart",
    namespace = "kyverno",
    release_name = "kyverno",
    # Upstream kyverno chart runs admission controller components that need root
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/kyverno:values.yaml",
        "values.yaml",
    ],
)

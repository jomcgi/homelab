load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "kyverno",
    chart = "projects/platform/kyverno/deploy",
    chart_files = ":chart",
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
        "values.yaml",
        "values-prod.yaml",
    ],
)

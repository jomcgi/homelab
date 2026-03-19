load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "linkerd",
    chart = "projects/platform/linkerd",
    chart_files = ":chart",
    namespace = "linkerd",
    release_name = "linkerd",
    # Upstream chart; containers don't mount /tmp
    semgrep_exclude_rules = [
        "require-tmp-emptydir",
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

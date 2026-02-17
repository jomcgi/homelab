load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "coredns-config",
    chart = "charts/coredns",
    chart_files = "//charts/coredns:chart",
    namespace = "kube-system",
    release_name = "coredns",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/coredns:values.yaml",
        "values.yaml",
    ],
)

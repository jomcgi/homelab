load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "oci-model-cache-operator",
    chart = "operators/oci-model-cache/helm/oci-model-cache-operator",
    chart_files = "//operators/oci-model-cache/helm/oci-model-cache-operator:chart",
    namespace = "oci-model-cache",
    release_name = "oci-model-cache-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//operators/oci-model-cache/helm/oci-model-cache-operator:values.yaml",
        "values.yaml",
    ],
)

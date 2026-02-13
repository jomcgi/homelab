load("//tools/argocd:defs.bzl", "helm_template_test")

helm_template_test(
    name = "template_test",
    chart = "operators/oci-model-cache/helm/oci-model-cache-operator",
    chart_files = "//operators/oci-model-cache/helm/oci-model-cache-operator:all_files",
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

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//operators/oci-model-cache/helm/oci-model-cache-operator:Chart.yaml",
        "//operators/oci-model-cache/helm/oci-model-cache-operator:all_files",
        "//operators/oci-model-cache/helm/oci-model-cache-operator:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template oci-model-cache-operator operators/oci-model-cache/helm/oci-model-cache-operator --namespace oci-model-cache --values operators/oci-model-cache/helm/oci-model-cache-operator/values.yaml --values overlays/dev/oci-model-cache/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for oci-model-cache-operator",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

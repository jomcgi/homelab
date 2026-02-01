load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/longhorn:Chart.yaml",
        "//charts/longhorn:values.yaml",
        "//charts/longhorn:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template longhorn charts/longhorn --namespace longhorn --values charts/longhorn/values.yaml --values overlays/cluster-critical/longhorn/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for longhorn",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/longhorn",
    chart_files = "//charts/longhorn:all_files",
    namespace = "longhorn",
    release_name = "longhorn",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/longhorn:values.yaml",
        "values.yaml",
    ],
)

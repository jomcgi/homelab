genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/longhorn:Chart.yaml",
        "//charts/longhorn:values.yaml",
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

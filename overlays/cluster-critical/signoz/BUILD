genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/signoz:Chart.yaml",
        "//charts/signoz:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template signoz charts/signoz --namespace signoz --values charts/signoz/values.yaml --values overlays/cluster-critical/signoz/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for signoz",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

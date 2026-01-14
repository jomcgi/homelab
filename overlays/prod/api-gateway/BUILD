genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/api-gateway:Chart.yaml",
        "//charts/api-gateway:all_files",
        "//charts/api-gateway:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template api-gateway charts/api-gateway --namespace api-gateway --values charts/api-gateway/values.yaml --values overlays/prod/api-gateway/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for api-gateway",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

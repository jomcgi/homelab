genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/marine:Chart.yaml",
        "//charts/marine:values.yaml",
        "//charts/marine:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template marine charts/marine --namespace marine --values charts/marine/values.yaml --values overlays/dev/marine/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for marine",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

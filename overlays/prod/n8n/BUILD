genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/n8n:Chart.yaml",
        "//charts/n8n:values.yaml",
        "//charts/n8n:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template n8n charts/n8n --namespace n8n --values charts/n8n/values.yaml --values overlays/prod/n8n/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-n8n",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

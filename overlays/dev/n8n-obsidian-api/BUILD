genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/n8n-obsidian-api:Chart.yaml",
        "//charts/n8n-obsidian-api:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template n8n-obsidian-api charts/n8n-obsidian-api --namespace n8n --values charts/n8n-obsidian-api/values.yaml --values charts/n8n-obsidian-api/values.yaml --values overlays/dev/n8n-obsidian-api/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for n8n-obsidian-api",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

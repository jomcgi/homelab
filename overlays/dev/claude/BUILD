genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/claude:Chart.yaml",
        "//charts/claude:all_files",
        "//charts/claude:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template claude charts/claude --namespace claude --values charts/claude/values.yaml --values overlays/dev/claude/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for claude",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

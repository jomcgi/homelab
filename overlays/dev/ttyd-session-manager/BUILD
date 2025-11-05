genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/ttyd-session-manager:Chart.yaml",
        "//charts/ttyd-session-manager:all_files",
        "//charts/ttyd-session-manager:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template ttyd-session-manager charts/ttyd-session-manager --namespace ttyd-sessions --values charts/ttyd-session-manager/values.yaml --values overlays/dev/ttyd-session-manager/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for ttyd-session-manager",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

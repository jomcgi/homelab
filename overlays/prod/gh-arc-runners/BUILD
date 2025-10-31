genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/gh-arc-runners:Chart.yaml",
        "//charts/gh-arc-runners:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template gh-arc-runners charts/gh-arc-runners --namespace gh-arc-runners --values charts/gh-arc-runners/values.yaml --values overlays/prod/gh-arc-runners/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for gh-arc-runners",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

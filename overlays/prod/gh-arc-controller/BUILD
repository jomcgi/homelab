genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/gh-arc-controller:Chart.yaml",
        "//charts/gh-arc-controller:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template gh-arc-controller charts/gh-arc-controller --namespace gh-arc-controller --values charts/gh-arc-controller/values.yaml --values overlays/prod/gh-arc-controller/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for gh-arc-controller",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

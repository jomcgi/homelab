genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/freshrss:Chart.yaml",
        "//charts/freshrss:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template freshrss charts/freshrss --namespace freshrss --values charts/freshrss/values.yaml --values charts/freshrss/values.yaml --values overlays/dev/freshrss/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for freshrss",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

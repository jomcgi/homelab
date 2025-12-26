genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/trips:Chart.yaml",
        "//charts/trips:values.yaml",
        "//charts/trips:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template trips charts/trips --namespace trips --values charts/trips/values.yaml --values overlays/prod/trips/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-trips",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

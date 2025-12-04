genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/fizzy:Chart.yaml",
        "//charts/fizzy:values.yaml",
        "//charts/fizzy:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template fizzy charts/fizzy --namespace fizzy --values charts/fizzy/values.yaml --values overlays/dev/fizzy/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for fizzy",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

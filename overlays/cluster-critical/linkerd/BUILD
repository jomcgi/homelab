genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/linkerd:Chart.yaml",
        "//charts/linkerd:all_files",
        "//charts/linkerd:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template linkerd charts/linkerd --namespace linkerd --values charts/linkerd/values.yaml --values overlays/cluster-critical/linkerd/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for linkerd",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

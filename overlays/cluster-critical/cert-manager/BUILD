genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/cert-manager:Chart.yaml",
        "//charts/cert-manager:all_files",
        "//charts/cert-manager:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cert-manager charts/cert-manager --namespace cert-manager --values charts/cert-manager/values.yaml --values overlays/cluster-critical/cert-manager/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cert-manager",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

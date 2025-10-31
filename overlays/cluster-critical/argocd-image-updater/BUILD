genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/argocd-image-updater:Chart.yaml",
        "//charts/argocd-image-updater:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template argocd-image-updater charts/argocd-image-updater --namespace argocd --values charts/argocd-image-updater/values.yaml --values charts/argocd-image-updater/values.yaml --values overlays/cluster-critical/argocd-image-updater/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for argocd-image-updater",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

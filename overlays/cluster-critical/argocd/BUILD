genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "//charts/argocd:Chart.yaml",
        "//charts/argocd:values.yaml",
        "//clusters/homelab/argocd:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template argocd charts/argocd --namespace argocd --values charts/argocd/values.yaml --values charts/argocd/values.yaml --values clusters/homelab/argocd/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for argocd",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

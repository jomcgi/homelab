genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/cloudflare-tunnel:Chart.yaml",
        "//charts/cloudflare-tunnel:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cluster-ingress charts/cloudflare-tunnel --namespace ingress --values charts/cloudflare-tunnel/values.yaml --values overlays/prod/cloudflare-tunnel/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cluster-ingress",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

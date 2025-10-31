genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//operators/cloudflare/helm/cloudflare-operator:Chart.yaml",
        "//operators/cloudflare/helm/cloudflare-operator:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cloudflare-operator operators/cloudflare/helm/cloudflare-operator --namespace cloudflare --values operators/cloudflare/helm/cloudflare-operator/values.yaml --values overlays/dev/cloudflare-operator/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cloudflare-operator",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

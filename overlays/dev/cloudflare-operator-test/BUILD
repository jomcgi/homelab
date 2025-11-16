genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/cloudflare-operator-test:Chart.yaml",
        "//charts/cloudflare-operator-test:all_files",
        "//charts/cloudflare-operator-test:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cloudflare-operator-test charts/cloudflare-operator-test --namespace cloudflare-operator-test --values charts/cloudflare-operator-test/values.yaml --values overlays/dev/cloudflare-operator-test/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cloudflare-operator-test",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

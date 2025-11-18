genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/coredns:Chart.yaml",
        "//charts/coredns:all_files",
        "//charts/coredns:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template coredns charts/coredns --namespace kube-system --values charts/coredns/values.yaml --values overlays/cluster-critical/coredns/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for coredns-config",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

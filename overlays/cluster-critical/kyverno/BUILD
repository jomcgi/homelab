genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/kyverno:Chart.yaml",
        "//charts/kyverno:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template kyverno charts/kyverno --namespace kyverno --values charts/kyverno/values.yaml --values overlays/cluster-critical/kyverno/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for kyverno",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

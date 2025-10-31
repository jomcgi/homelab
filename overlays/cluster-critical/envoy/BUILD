genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/envoy-gateway:Chart.yaml",
        "//charts/envoy-gateway:values.yaml",
        "//charts/envoy-gateway:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template envoy-gateway charts/envoy-gateway --namespace envoy --values charts/envoy-gateway/values.yaml --values overlays/cluster-critical/envoy/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for envoy-gateway",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

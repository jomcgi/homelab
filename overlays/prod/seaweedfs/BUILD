genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/seaweedfs:Chart.yaml",
        "//charts/seaweedfs:values.yaml",
        "//charts/seaweedfs:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template seaweedfs charts/seaweedfs --namespace seaweedfs --values charts/seaweedfs/values.yaml --values overlays/prod/seaweedfs/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-seaweedfs",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

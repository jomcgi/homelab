genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "//charts/nvidia-gpu-operator:Chart.yaml",
        "//charts/nvidia-gpu-operator:all_files",
        "//charts/nvidia-gpu-operator:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template nvidia-gpu-operator charts/nvidia-gpu-operator --namespace gpu-operator --values charts/nvidia-gpu-operator/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for nvidia-gpu-operator",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/vllm:Chart.yaml",
        "//charts/vllm:all_files",
        "//charts/vllm:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template vllm charts/vllm --namespace vllm --values charts/vllm/values.yaml --values overlays/prod/vllm/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-vllm",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

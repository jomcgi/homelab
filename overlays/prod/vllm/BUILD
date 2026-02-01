load("//tools/argocd:defs.bzl", "helm_template_test")

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

helm_template_test(
    name = "template_test",
    chart = "charts/vllm",
    chart_files = "//charts/vllm:all_files",
    namespace = "vllm",
    release_name = "vllm",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/vllm:values.yaml",
        "values.yaml",
    ],
)

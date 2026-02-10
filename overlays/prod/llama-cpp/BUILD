load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/llama-cpp:Chart.yaml",
        "//charts/llama-cpp:all_files",
        "//charts/llama-cpp:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template llama-cpp charts/llama-cpp --namespace llama-cpp --values charts/llama-cpp/values.yaml --values overlays/prod/llama-cpp/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-llama-cpp",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/llama-cpp",
    chart_files = "//charts/llama-cpp:all_files",
    namespace = "llama-cpp",
    release_name = "llama-cpp",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/llama-cpp:values.yaml",
        "values.yaml",
    ],
)

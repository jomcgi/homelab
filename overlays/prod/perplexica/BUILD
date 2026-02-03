load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/perplexica:Chart.yaml",
        "//charts/perplexica:all_files",
        "//charts/perplexica:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template perplexica charts/perplexica --namespace search --values charts/perplexica/values.yaml --values overlays/prod/perplexica/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-perplexica",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/perplexica",
    chart_files = "//charts/perplexica:all_files",
    namespace = "search",
    release_name = "perplexica",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/perplexica:values.yaml",
        "values.yaml",
    ],
)

load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/knowledge-graph:Chart.yaml",
        "//charts/knowledge-graph:all_files",
        "//charts/knowledge-graph:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template knowledge-graph charts/knowledge-graph --namespace knowledge-graph --values charts/knowledge-graph/values.yaml --values overlays/prod/knowledge-graph/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for knowledge-graph",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/knowledge-graph",
    chart_files = "//charts/knowledge-graph:all_files",
    namespace = "knowledge-graph",
    release_name = "knowledge-graph",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/knowledge-graph:values.yaml",
        "values.yaml",
    ],
)

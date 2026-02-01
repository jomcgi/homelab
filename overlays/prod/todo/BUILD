load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/todo:Chart.yaml",
        "//charts/todo:all_files",
        "//charts/todo:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template todo charts/todo --namespace todo --values charts/todo/values.yaml --values overlays/prod/todo/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for todo",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/todo",
    chart_files = "//charts/todo:all_files",
    namespace = "todo",
    release_name = "todo",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
    ],
)

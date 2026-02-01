load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/marine:Chart.yaml",
        "//charts/marine:values.yaml",
        "//charts/marine:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template marine charts/marine --namespace marine --values charts/marine/values.yaml --values overlays/dev/marine/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for marine",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/marine",
    chart_files = "//charts/marine:all_files",
    namespace = "marine",
    release_name = "marine",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/marine:values.yaml",
        "values.yaml",
    ],
)

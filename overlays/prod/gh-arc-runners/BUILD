load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/gh-arc-runners:Chart.yaml",
        "//charts/gh-arc-runners:all_files",
        "//charts/gh-arc-runners:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template gh-arc-runners charts/gh-arc-runners --namespace gh-arc-runners --values charts/gh-arc-runners/values.yaml --values overlays/prod/gh-arc-runners/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for gh-arc-runners",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/gh-arc-runners",
    chart_files = "//charts/gh-arc-runners:all_files",
    namespace = "gh-arc-runners",
    release_name = "gh-arc-runners",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/gh-arc-runners:values.yaml",
        "values.yaml",
    ],
)

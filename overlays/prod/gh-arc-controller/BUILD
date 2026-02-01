load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/gh-arc-controller:Chart.yaml",
        "//charts/gh-arc-controller:values.yaml",
        "//charts/gh-arc-controller:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template gh-arc-controller charts/gh-arc-controller --namespace gh-arc-controller --values charts/gh-arc-controller/values.yaml --values overlays/prod/gh-arc-controller/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for gh-arc-controller",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/gh-arc-controller",
    chart_files = "//charts/gh-arc-controller:all_files",
    namespace = "gh-arc-controller",
    release_name = "gh-arc-controller",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/gh-arc-controller:values.yaml",
        "values.yaml",
    ],
)

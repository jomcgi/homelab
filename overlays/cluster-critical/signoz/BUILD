load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/signoz:Chart.yaml",
        "//charts/signoz:values.yaml",
        "//charts/signoz:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template signoz charts/signoz --namespace signoz --values charts/signoz/values.yaml --values overlays/cluster-critical/signoz/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for signoz",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/signoz",
    chart_files = "//charts/signoz:all_files",
    namespace = "signoz",
    release_name = "signoz",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/signoz:values.yaml",
        "values.yaml",
    ],
)

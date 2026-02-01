load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/signoz-dashboard-sidecar:Chart.yaml",
        "//charts/signoz-dashboard-sidecar:values.yaml",
        "//charts/signoz-dashboard-sidecar:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template signoz-dashboard-sidecar charts/signoz-dashboard-sidecar --namespace signoz --values charts/signoz-dashboard-sidecar/values.yaml --values overlays/cluster-critical/signoz-dashboard-sidecar/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for signoz-dashboard-sidecar",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/signoz-dashboard-sidecar",
    chart_files = "//charts/signoz-dashboard-sidecar:all_files",
    namespace = "signoz",
    release_name = "signoz-dashboard-sidecar",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/signoz-dashboard-sidecar:values.yaml",
        "values.yaml",
    ],
)

load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/nats:Chart.yaml",
        "//charts/nats:values.yaml",
        "//charts/nats:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template nats charts/nats --namespace nats --values charts/nats/values.yaml --values overlays/prod/nats/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-nats",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/nats",
    chart_files = "//charts/nats:all_files",
    namespace = "nats",
    release_name = "nats",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/nats:values.yaml",
        "values.yaml",
    ],
)

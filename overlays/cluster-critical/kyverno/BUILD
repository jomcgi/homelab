load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/kyverno:Chart.yaml",
        "//charts/kyverno:values.yaml",
        "//charts/kyverno:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template kyverno charts/kyverno --namespace kyverno --values charts/kyverno/values.yaml --values overlays/cluster-critical/kyverno/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for kyverno",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/kyverno",
    chart_files = "//charts/kyverno:all_files",
    namespace = "kyverno",
    release_name = "kyverno",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/kyverno:values.yaml",
        "values.yaml",
    ],
)

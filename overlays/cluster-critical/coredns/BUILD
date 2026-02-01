load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/coredns:Chart.yaml",
        "//charts/coredns:all_files",
        "//charts/coredns:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template coredns charts/coredns --namespace kube-system --values charts/coredns/values.yaml --values overlays/cluster-critical/coredns/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for coredns-config",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/coredns",
    chart_files = "//charts/coredns:all_files",
    namespace = "kube-system",
    release_name = "coredns",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/coredns:values.yaml",
        "values.yaml",
    ],
)

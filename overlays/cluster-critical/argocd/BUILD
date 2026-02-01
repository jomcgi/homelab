load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "//charts/argocd:Chart.yaml",
        "//charts/argocd:values.yaml",
        "//clusters/homelab/argocd:values.yaml",
        "//charts/argocd:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template argocd charts/argocd --namespace argocd --values charts/argocd/values.yaml --values clusters/homelab/argocd/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for argocd",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/argocd",
    chart_files = "//charts/argocd:all_files",
    namespace = "argocd",
    release_name = "argocd",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/argocd:values.yaml",
        "//clusters/homelab/argocd:values.yaml",
    ],
)

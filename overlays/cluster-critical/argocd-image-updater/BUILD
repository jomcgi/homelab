load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/argocd-image-updater:Chart.yaml",
        "//charts/argocd-image-updater:values.yaml",
        "//charts/argocd-image-updater:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template argocd-image-updater charts/argocd-image-updater --namespace argocd --values charts/argocd-image-updater/values.yaml --values overlays/cluster-critical/argocd-image-updater/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for argocd-image-updater",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/argocd-image-updater",
    chart_files = "//charts/argocd-image-updater:all_files",
    namespace = "argocd",
    release_name = "argocd-image-updater",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/argocd-image-updater:values.yaml",
        "values.yaml",
    ],
)

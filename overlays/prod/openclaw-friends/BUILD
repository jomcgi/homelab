load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/openclaw:Chart.yaml",
        "//charts/openclaw:all_files",
        "//charts/openclaw:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template openclaw-friends charts/openclaw --namespace openclaw --values charts/openclaw/values.yaml --values overlays/prod/openclaw-friends/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for prod-openclaw-friends",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/openclaw",
    chart_files = "//charts/openclaw:all_files",
    namespace = "openclaw",
    release_name = "openclaw-friends",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/openclaw:values.yaml",
        "values.yaml",
    ],
)

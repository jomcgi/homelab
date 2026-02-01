load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/stargazer:Chart.yaml",
        "//charts/stargazer:values.yaml",
        "//charts/stargazer:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template stargazer charts/stargazer --namespace stargazer --values charts/stargazer/values.yaml --values overlays/dev/stargazer/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for stargazer",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/stargazer",
    chart_files = "//charts/stargazer:all_files",
    namespace = "stargazer",
    release_name = "stargazer",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/stargazer:values.yaml",
        "values.yaml",
    ],
)

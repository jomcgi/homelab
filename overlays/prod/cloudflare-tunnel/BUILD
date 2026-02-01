load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/cloudflare-tunnel:Chart.yaml",
        "//charts/cloudflare-tunnel:values.yaml",
        "//charts/cloudflare-tunnel:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cluster-ingress charts/cloudflare-tunnel --namespace ingress --values charts/cloudflare-tunnel/values.yaml --values overlays/prod/cloudflare-tunnel/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cluster-ingress",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/cloudflare-tunnel",
    chart_files = "//charts/cloudflare-tunnel:all_files",
    namespace = "ingress",
    release_name = "cluster-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-tunnel:values.yaml",
        "values.yaml",
    ],
)

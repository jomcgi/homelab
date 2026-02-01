load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//operators/cloudflare/helm/cloudflare-operator:Chart.yaml",
        "//operators/cloudflare/helm/cloudflare-operator:values.yaml",
        "//operators/cloudflare/helm/cloudflare-operator:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cloudflare-operator operators/cloudflare/helm/cloudflare-operator --namespace cloudflare --values operators/cloudflare/helm/cloudflare-operator/values.yaml --values overlays/dev/cloudflare-operator/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cloudflare-operator",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "operators/cloudflare/helm/cloudflare-operator",
    chart_files = "//operators/cloudflare/helm/cloudflare-operator:all_files",
    namespace = "cloudflare",
    release_name = "cloudflare-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//operators/cloudflare/helm/cloudflare-operator:values.yaml",
        "values.yaml",
    ],
)

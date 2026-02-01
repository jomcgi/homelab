load("//tools/argocd:defs.bzl", "helm_template_test")

genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/cloudflare-operator-test:Chart.yaml",
        "//charts/cloudflare-operator-test:all_files",
        "//charts/cloudflare-operator-test:values.yaml",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template cloudflare-operator-test charts/cloudflare-operator-test --namespace cloudflare-operator-test --values charts/cloudflare-operator-test/values.yaml --values overlays/dev/cloudflare-operator-test/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for cloudflare-operator-test",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

helm_template_test(
    name = "template_test",
    chart = "charts/cloudflare-operator-test",
    chart_files = "//charts/cloudflare-operator-test:all_files",
    namespace = "cloudflare-operator-test",
    release_name = "cloudflare-operator-test",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-operator-test:values.yaml",
        "values.yaml",
    ],
)

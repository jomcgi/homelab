genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/gh-arc-runners:Chart.yaml",
        "//charts/gh-arc-runners:values.yaml",
        "//charts/gh-arc-runners:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template gh-arc-bazel-runner charts/gh-arc-runners --namespace gh-arc-runners --values charts/gh-arc-runners/values.yaml --values overlays/prod/gh-arc-bazel-runner/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for gh-arc-bazel-runner",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

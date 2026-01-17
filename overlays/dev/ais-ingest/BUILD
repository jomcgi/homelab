genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/ais-ingest:Chart.yaml",
        "//charts/ais-ingest:values.yaml",
        "//charts/ais-ingest:all_files",
    ],
    outs = ["manifests/all.yaml"],
    cmd = "$(location @multitool//tools/helm) template ais-ingest charts/ais-ingest --namespace ais-ingest --values charts/ais-ingest/values.yaml --values overlays/dev/ais-ingest/values.yaml > $@",
    local = True,
    message = "Rendering Helm manifests for ais-ingest",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

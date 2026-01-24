genrule(
    name = "render_manifests",
    srcs = [
        "application.yaml",
        "values.yaml",
        "//charts/seaweedfs:Chart.yaml",
        "//charts/seaweedfs:values.yaml",
        "//charts/seaweedfs:all_files",
    ],
    outs = ["manifests/all.yaml"],
    # Filter out secret-seaweedfs-db - it contains hardcoded placeholders from upstream chart
    # but is never used (MySQL is disabled, we use LevelDB for filer metadata)
    cmd = """$(location @multitool//tools/helm) template seaweedfs charts/seaweedfs --namespace seaweedfs --values charts/seaweedfs/values.yaml --values overlays/prod/seaweedfs/values.yaml | awk '
        BEGIN { skip=0; buffer="" }
        /^---/ { if (skip) { skip=0 } else { print buffer } buffer="---\\n"; next }
        /name: secret-seaweedfs-db/ { skip=1 }
        { buffer = buffer $$0 "\\n" }
        END { if (!skip) print buffer }
    ' > $@""",
    local = True,
    message = "Rendering Helm manifests for prod-seaweedfs",
    tags = ["manual"],
    tools = [
        "//tools/argocd:render-manifests.sh",
        "@multitool//tools/helm",
    ],
    visibility = ["//visibility:public"],
)

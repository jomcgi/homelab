load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "goose-sandboxes",
    chart = "charts/goose-sandboxes",
    chart_files = "//charts/goose-sandboxes:chart",
    namespace = "goose-sandboxes",
    release_name = "goose-sandboxes",
    # Agent pods need writable fs for git, npm, build tools
    semgrep_exclude_rules = ["writable-filesystem-container"],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/goose-sandboxes:values.yaml",
        "values.yaml",
    ],
)

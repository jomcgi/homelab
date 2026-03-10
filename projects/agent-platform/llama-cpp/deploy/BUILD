load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "llama-cpp",
    chart = "projects/agent-platform/llama-cpp/deploy",
    chart_files = ":chart",
    namespace = "llama-cpp",
    release_name = "llama-cpp",
    # readOnlyRootFilesystem may cause issues with model loading
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)

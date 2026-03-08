load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "llama-cpp",
    chart = "charts/llama-cpp",
    chart_files = "//charts/llama-cpp:chart",
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
        "//charts/llama-cpp:values.yaml",
        "values.yaml",
    ],
)

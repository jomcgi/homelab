load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "marine",
    chart = "charts/marine",
    chart_files = "//charts/marine:chart",
    namespace = "marine",
    release_name = "marine",
    # Uses aspect_rules_py which needs writable FS and runs as root
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/marine:values.yaml",
        "values.yaml",
    ],
)

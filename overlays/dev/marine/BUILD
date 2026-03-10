load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "marine",
    chart = "projects/ships/deploy",
    chart_files = "//projects/ships/deploy:chart",
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
        "//projects/ships/deploy:values.yaml",
        "values.yaml",
    ],
)

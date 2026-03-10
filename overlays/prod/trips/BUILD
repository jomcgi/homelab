load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "trips",
    chart = "projects/trips/deploy",
    chart_files = "//projects/trips/deploy:chart",
    namespace = "trips",
    release_name = "trips",
    # api container uses aspect_rules_py which needs writable FS and runs as root
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//projects/trips/deploy:values.yaml",
        "values.yaml",
    ],
)

load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "stargazer",
    chart = "projects/stargazer/deploy",
    chart_files = "//projects/stargazer/deploy:chart",
    namespace = "stargazer",
    release_name = "stargazer",
    # CronJob uses aspect_rules_py which needs writable FS and runs as root
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//projects/stargazer/deploy:values.yaml",
        "values.yaml",
    ],
)

load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "gh-arc-runners",
    chart = "charts/gh-arc-runners",
    chart_files = "//charts/gh-arc-runners:chart",
    namespace = "gh-arc-runners",
    release_name = "gh-arc-runners",
    # GitHub Actions runners use privileged containers for Docker-in-Docker builds
    semgrep_exclude_rules = [
        "no-privileged",
        "yaml.kubernetes.security.privileged-container.privileged-container",
        "yaml.kubernetes.security.allow-privilege-escalation.allow-privilege-escalation",
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/gh-arc-runners:values.yaml",
        "values.yaml",
    ],
)

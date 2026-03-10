load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "nvidia-gpu-operator",
    chart = "projects/platform/nvidia-gpu-operator",
    chart_files = ":chart",
    namespace = "gpu-operator",
    release_name = "nvidia-gpu-operator",
    # GPU drivers require privileged containers; upstream chart doesn't expose securityContext
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.privileged-container.privileged-container",
        "yaml.kubernetes.security.allow-privilege-escalation.allow-privilege-escalation",
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = ["values.yaml"],
)

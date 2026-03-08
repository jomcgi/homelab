load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "todo",
    chart = "charts/todo",
    chart_files = "//charts/todo:chart",
    namespace = "todo",
    release_name = "todo",
    # git-clone init container needs root, nginx needs writable FS
    semgrep_exclude_rules = [
        "yaml.kubernetes.security.writable-filesystem-container.writable-filesystem-container",
        "yaml.kubernetes.security.run-as-non-root.run-as-non-root",
    ],
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
    ],
)

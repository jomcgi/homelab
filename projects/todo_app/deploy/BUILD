load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/todo_app/image:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "todo",
    chart = "projects/todo_app/deploy",
    chart_files = ":chart",
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
        "values.yaml",
        "values-prod.yaml",
    ],
)

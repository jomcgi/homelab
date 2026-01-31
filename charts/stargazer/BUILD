load("//tools/argocd:defs.bzl", "chart_files", "helm_lint_test")

chart_files(
    name = "all_files",
    visibility = ["//overlays/dev/stargazer:__pkg__"],
)

helm_lint_test(
    name = "lint_test",
    tags = ["chart"],
)

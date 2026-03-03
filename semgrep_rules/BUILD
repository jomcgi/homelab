package(default_visibility = ["//visibility:public"])

filegroup(
    name = "shell_rules",
    srcs = glob(["shell/*.yaml"]),
)

filegroup(
    name = "bazel_rules",
    srcs = glob(["bazel/*.yaml"]),
)

filegroup(
    name = "dockerfile_rules",
    srcs = glob(["dockerfile/*.yaml"]),
)

filegroup(
    name = "kubernetes_rules",
    srcs = glob(
        ["kubernetes/*.yaml"],
        allow_empty = True,
    ),
)

filegroup(
    name = "all_rules",
    srcs = glob(["**/*.yaml"]),
)

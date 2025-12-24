load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

sh_binary(
    name = "signoz-mcp-wrapper",
    srcs = ["signoz-mcp-wrapper.sh"],
)

sh_binary(
    name = "generate-push-all",
    srcs = ["generate-push-all.sh"],
    visibility = ["//:__subpackages__"],
)

sh_binary(
    name = "generate-render-all",
    srcs = ["generate-render-all.sh"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "scripts",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

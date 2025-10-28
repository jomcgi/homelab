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

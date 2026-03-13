load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

pkg_tar(
    name = "src_tar",
    srcs = glob(["src/**/*.ts"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/src",
    strip_prefix = "src",
)

pkg_tar(
    name = "config_tar",
    srcs = [
        "package.json",
        "tsconfig.json",
    ],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app",
)

apko_image(
    name = "image",
    config = "//projects/agent_platform/chat_bot/image:apko.yaml",
    contents = "@chat_bot_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/agent-platform/chat-bot",
    tars = [
        ":src_tar",
        ":config_tar",
    ],
)

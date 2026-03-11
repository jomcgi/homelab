load("//bazel/vitepress:defs.bzl", "vitepress_filegroup")

vitepress_filegroup(
    name = "docs",
    srcs = glob(["*.md"]) + glob(["decisions/**/*.md"]),
    visibility = ["//projects/websites/docs.jomcgi.dev:__pkg__"],
    vitepress_path = "docs",
)

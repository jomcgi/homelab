load("//rules_vitepress:defs.bzl", "vitepress_filegroup")

vitepress_filegroup(
    name = "docs",
    srcs = glob(["*.md"]) + glob(["decisions/**/*.md"]),
    vitepress_path = "architecture",
    visibility = ["//websites/docs.jomcgi.dev:__pkg__"],
)

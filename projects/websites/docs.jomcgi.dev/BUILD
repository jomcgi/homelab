load("@npm//projects/websites/docs.jomcgi.dev:vitepress/package_json.bzl", vitepress_bin = "bin")
load("@npm//projects/websites/docs.jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")
load("//bazel/vitepress:site.bzl", "vitepress_site")

# VitePress binary for building
vitepress_bin.vitepress_binary(name = "vitepress")

# Wrangler binary for Cloudflare Pages deployment
wrangler_bin.wrangler_binary(name = "wrangler")

# Validate sidebar/nav links match actual files
py_test(
    name = "config_links_test",
    srcs = ["config_links_test.py"],
    data = [
        ".vitepress/adr-sidebar.json",
        ".vitepress/config.js",
        "//docs",
    ],
    deps = [
        "@pip//pytest",
    ],
)

# Build and deploy the docs site
vitepress_site(
    name = "docs",
    content = [
        "//docs:docs",
    ],
    extra_srcs = [
        ".vitepress/adr-sidebar.json",
        "index.md",
    ],
    vitepress_config = ".vitepress/config.js",
    wrangler_project = "docs-jomcgi-dev",
)

semgrep_test(
    name = "config_links_test_semgrep_test",
    srcs = ["config_links_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

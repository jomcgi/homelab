load("@npm//projects/websites/docs.jomcgi.dev:vitepress/package_json.bzl", vitepress_bin = "bin")
load("@npm//projects/websites/docs.jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")
load("//bazel/vitepress:site.bzl", "vitepress_site")

# VitePress binary for building
vitepress_bin.vitepress_binary(name = "vitepress")

# Wrangler binary for Cloudflare Pages deployment
wrangler_bin.wrangler_binary(name = "wrangler")

# Build and deploy the docs site
vitepress_site(
    name = "docs",
    content = [
        "//docs:docs",
    ],
    extra_srcs = [
        "index.md",
    ],
    vitepress_config = ".vitepress/config.js",
    wrangler_project = "docs-jomcgi-dev",
)

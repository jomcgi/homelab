load("@npm//:defs.bzl", "npm_link_all_packages")

# hikes.jomcgi.dev - Static site, no build step needed
# gazelle:wrangler_dist :public
load("@npm//projects/websites/hikes.jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")
load("//bazel/wrangler:defs.bzl", "wrangler_pages")

# Link npm packages for this workspace package
npm_link_all_packages(name = "node_modules")

# Wrangler binary for Cloudflare Pages deployment
wrangler_bin.wrangler_binary(name = "wrangler")

# Static assets served directly (no build step)
filegroup(
    name = "public",
    srcs = glob(["public/**/*"]),
    visibility = ["//visibility:public"],
)

# Cloudflare Pages deployment
wrangler_pages(
    name = "hikes",
    dist = ":public",
    project_name = "jomcgi-hikes",
    visibility = ["//projects/websites:__pkg__"],
    wrangler = ":wrangler",
)

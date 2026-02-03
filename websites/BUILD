load("@rules_multirun//:defs.bzl", "multirun")

# Centralized Cloudflare Pages deployment target
# Run `bazel run //websites:push_all_pages` to deploy all CF Pages sites
multirun(
    name = "push_all_pages",
    commands = [
        "//websites/trips.jomcgi.dev:trips_esbuild.push",
    ],
    jobs = 0,  # 0 means unlimited parallelism
    visibility = ["//visibility:public"],
)

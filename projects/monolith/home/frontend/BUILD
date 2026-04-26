load("@aspect_rules_js//js:defs.bzl", "js_library")

# Source files for the home service's SvelteKit routes/components/styles.
# These are reached from the SvelteKit shell at //projects/monolith/frontend
# via symlinks under src/lib/public and src/routes/{public,private}, and
# must therefore be in the build action's input set so Vite can resolve
# them in the Bazel sandbox.
js_library(
    name = "src",
    srcs = glob(
        ["**/*"],
        allow_empty = True,
        exclude = [
            "BUILD",
            "node_modules/**",
            "**/*.test.js",
        ],
    ),
    visibility = ["//projects/monolith/frontend:__pkg__"],
)

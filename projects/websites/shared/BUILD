load("@aspect_rules_js//js:defs.bzl", "js_library")

# All shared CSS — including nav/nav.css under the subdirectory.
js_library(
    name = "css",
    srcs = glob(["**/*.css"]),
    visibility = [
        "//projects/monolith/frontend:__subpackages__",
        "//projects/websites:__subpackages__",
    ],
)

# Shared nav renderers + the link list. Astro consumes Nav.astro;
# SvelteKit consumes Nav.svelte; both import routes.js.
js_library(
    name = "nav",
    srcs = glob([
        "nav/*.astro",
        "nav/*.svelte",
        "nav/*.js",
    ]),
    visibility = [
        "//projects/monolith/frontend:__subpackages__",
        "//projects/websites:__subpackages__",
    ],
)

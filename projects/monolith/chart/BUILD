load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//bazel/helm:defs.bzl", "helm_chart")

filegroup(
    name = "migrations",
    srcs = glob([
        "migrations/*.sql",
        "migrations/atlas.sum",
    ]),
    visibility = ["//projects/monolith:__subpackages__"],
)

sh_test(
    name = "atlas_sum_test",
    srcs = ["//bazel/tools/format:validate-atlas-sum.sh"],
    data = [
        ":migrations",
        "@multitool//tools/atlas",
    ],
    env = {
        "ATLAS_BIN": "$(rootpath @multitool//tools/atlas)",
        "MIGRATIONS_DIR": "projects/monolith/chart/migrations",
    },
)

sh_test(
    name = "obsidian_readiness_probe_test",
    srcs = ["obsidian_readiness_probe_test.sh"],
    args = [
        "$(rootpath @multitool//tools/helm)",
        "$(rootpath :chart.package)",
        "$(rootpath //projects/monolith/obsidian-image:entrypoint.sh)",
    ],
    data = [
        ":chart.package",
        "//projects/monolith/obsidian-image:entrypoint.sh",
        "@multitool//tools/helm",
    ],
)

helm_chart(
    name = "chart",
    images = {
        "backend.image": "//projects/monolith:image.info",
        "frontend.image": "//projects/monolith/frontend:image.info",
        "knowledge.headlessSync.image": "//projects/monolith/obsidian-image:image.info",
    },
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

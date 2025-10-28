load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "api",
    srcs = [
        "cloudflaretunnel_types.go",
        "conditions.go",
        "groupversion_info.go",
        "zz_generated.deepcopy.go",
    ],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/api/v1",
    visibility = ["//visibility:public"],
    deps = [
        "@io_k8s_apimachinery//pkg/runtime:go_default_library",
        "@io_k8s_apimachinery//pkg/runtime/schema:go_default_library",
    ],
)

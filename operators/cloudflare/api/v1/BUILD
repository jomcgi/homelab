load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "api",
    srcs = [
        "cloudflareaccesspolicy_types.go",
        "cloudflaretunnel_types.go",
        "conditions.go",
        "groupversion_info.go",
        "zz_generated.deepcopy.go",
    ],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/api/v1",
    visibility = ["//visibility:public"],
    deps = [
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_sigs_controller_runtime//pkg/scheme",
        "@io_k8s_sigs_gateway_api//apis/v1:apis",
    ],
)

load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "api",
    srcs = [
        "cloudflareaccesspolicy_types.go",
        "cloudflaretunnel_types.go",
        "cloudflaretunnel_webhook.go",
        "conditions.go",
        "groupversion_info.go",
        "zz_generated.deepcopy.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1",
    visibility = ["//visibility:public"],
    deps = [
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_apimachinery//pkg/util/validation/field",
        "@io_k8s_sigs_controller_runtime//:controller-runtime",
        "@io_k8s_sigs_controller_runtime//pkg/log",
        "@io_k8s_sigs_controller_runtime//pkg/scheme",
        "@io_k8s_sigs_controller_runtime//pkg/webhook/admission",
        "@io_k8s_sigs_gateway_api//apis/v1:apis",
    ],
)

go_test(
    name = "api_test",
    srcs = ["cloudflaretunnel_webhook_test.go"],
    embed = [":api"],
    deps = ["@io_k8s_apimachinery//pkg/apis/meta/v1:meta"],
)

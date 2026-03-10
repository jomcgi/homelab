load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "api",
    srcs = [
        "groupversion_info.go",
        "modelcache_types.go",
        "zz_generated.deepcopy.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1",
    visibility = ["//visibility:public"],
    deps = [
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_sigs_controller_runtime//pkg/scheme",
    ],
)

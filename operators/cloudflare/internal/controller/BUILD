load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "controller",
    srcs = ["cloudflaretunnel_controller.go"],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/internal/controller",
    visibility = ["//operators/cloudflare:__subpackages__"],
    deps = [
        "//operators/cloudflare/api/v1:api",
        "//operators/cloudflare/internal/cloudflare",
        "//operators/cloudflare/internal/telemetry",
        "@com_github_cloudflare_cloudflare_go//:cloudflare-go",
        "@io_k8s_api//apps/v1:apps",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/errors",
        "@io_k8s_apimachinery//pkg/api/meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/types",
        "@io_k8s_client_go//util/workqueue",
        "@io_k8s_sigs_controller_runtime//:controller-runtime",
        "@io_k8s_sigs_controller_runtime//pkg/client",
        "@io_k8s_sigs_controller_runtime//pkg/controller/controllerutil",
        "@io_k8s_sigs_controller_runtime//pkg/log",
        "@io_k8s_sigs_controller_runtime//pkg/reconcile",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel//codes",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)

go_test(
    name = "controller_test",
    srcs = [
        "cloudflaretunnel_controller_test.go",
        "suite_test.go",
    ],
    embed = [":controller"],
    tags = ["manual"],  # Requires envtest binaries - run manually with proper setup
    deps = [
        "//operators/cloudflare/api/v1:api",
        "//operators/cloudflare/internal/cloudflare",
        "@com_github_cloudflare_cloudflare_go//:cloudflare-go",
        "@com_github_onsi_ginkgo_v2//:ginkgo",
        "@com_github_onsi_gomega//:gomega",
        "@io_k8s_apimachinery//pkg/api/errors",
        "@io_k8s_apimachinery//pkg/api/meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/types",
        "@io_k8s_client_go//kubernetes/scheme",
        "@io_k8s_client_go//rest",
        "@io_k8s_sigs_controller_runtime//pkg/client",
        "@io_k8s_sigs_controller_runtime//pkg/envtest",
        "@io_k8s_sigs_controller_runtime//pkg/log",
        "@io_k8s_sigs_controller_runtime//pkg/log/zap",
        "@io_k8s_sigs_controller_runtime//pkg/reconcile",
    ],
)

load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:go_image.bzl", "go_image")

# Package UI dist into a container layer at /opt/ui/
genrule(
    name = "ui_dist_tar",
    srcs = ["//projects/agent_platform/orchestrator/ui:build_dist"],
    outs = ["ui_dist.tar"],
    cmd = """
        WORK=$$(mktemp -d)
        DEST="$$WORK/opt/ui"
        mkdir -p "$$DEST"
        cp -rL $(location //projects/agent_platform/orchestrator/ui:build_dist)/. "$$DEST/"
        tar -cf $@ -C "$$WORK" .
    """,
)

py_library(
    name = "orchestrator_py",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

# gazelle:map_kind go_test go_test @rules_go//go:def.bzl

go_library(
    name = "orchestrator_lib",
    srcs = [
        "api.go",
        "clean.go",
        "consumer.go",
        "main.go",
        "model.go",
        "reconcile.go",
        "result.go",
        "sandbox.go",
        "store.go",
        "summarizer.go",
        "ui.go",
        "watchdog.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/orchestrator",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@com_github_oklog_ulid_v2//:ulid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/errors",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
    ],
)

go_binary(
    name = "agent-orchestrator",
    embed = [":orchestrator_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "orchestrator_unit_test",
    srcs = [
        "api_test.go",
        "clean_test.go",
        "consumer_test.go",
        "model_test.go",
        "reconcile_test.go",
        "result_test.go",
        "sandbox_k8s_test.go",
        "sandbox_test.go",
        "summarizer_test.go",
        "ui_test.go",
        "watchdog_test.go",
    ],
    embed = [":orchestrator_lib"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic/fake",
        "@io_k8s_client_go//kubernetes/fake",
    ],
)

go_test(
    name = "orchestrator_test",
    srcs = [
        "api_test.go",
        "clean_test.go",
        "consumer_test.go",
        "main_test.go",
        "model_test.go",
        "reconcile_test.go",
        "result_test.go",
        "sandbox_k8s_test.go",
        "sandbox_test.go",
        "store_test.go",
        "summarizer_test.go",
        "ui_test.go",
        "watchdog_test.go",
    ],
    embed = [":orchestrator_lib"],
    tags = ["manual"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic/fake",
        "@io_k8s_client_go//kubernetes/fake",
    ],
)

go_image(
    name = "image",
    binary = ":agent-orchestrator",
    extra_tars = [":ui_dist_tar"],
    repository = "ghcr.io/jomcgi/homelab/projects/agent_platform/orchestrator",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

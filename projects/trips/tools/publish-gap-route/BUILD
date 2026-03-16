load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//defusedxml",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

py_library(
    name = "publish-gap-route",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//defusedxml",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

py_test(
    name = "gap_route_test",
    srcs = ["gap_route_test.py"],
    imports = ["."],
    deps = [
        ":publish-gap-route",
        "@pip//defusedxml",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "gap_route_test_semgrep_test",
    srcs = ["gap_route_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

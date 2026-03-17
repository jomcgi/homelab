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
        "@pip//httpx",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

py_library(
    name = "delete-trip-points",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
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

# gazelle:resolve py main //projects/trips/tools/delete-trip-points:delete-trip-points
# gazelle:resolve py main.publish_delete //projects/trips/tools/delete-trip-points:delete-trip-points
py_test(
    name = "delete_trip_points_test",
    srcs = ["delete_trip_points_test.py"],
    imports = ["."],
    deps = [
        "//projects/trips/tools/delete-trip-points",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "delete_trip_points_test_semgrep_test",
    srcs = ["delete_trip_points_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

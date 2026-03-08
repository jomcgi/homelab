load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //scripts/publish-trip-images:publish-trip-images

py_library(
    name = "publish-trip-images",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//scripts/elevation",
        "@pip//boto3",
        "@pip//botocore",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//rich",
        "@pip//typer",
    ],
)

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "//scripts/elevation",
        "@pip//boto3",
        "@pip//botocore",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//rich",
        "@pip//typer",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//requirements:all.txt"],
    rules = ["//semgrep_rules:python_rules"],
    sca_rules = ["//semgrep_rules:sca_python_rules"],
    target = ":main",
)

py_test(
    name = "rebuild_test",
    srcs = ["rebuild_test.py"],
    imports = ["."],
    deps = [
        "//scripts/elevation",
        "//scripts/publish-trip-images",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "rebuild_test_semgrep_test",
    srcs = ["rebuild_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test")

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
    lockfiles = ["//requirements:all.txt"],
    rules = ["//semgrep_rules:python_rules"],
    sca_rules = ["//semgrep_rules:sca_python_rules"],
    target = ":main",
)

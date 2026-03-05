load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test", "semgrep_test")

py_library(
    name = "detect-wildlife",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//open_gopro",
        "@pip//typer",
    ],
)

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//open_gopro",
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
    sca_rules = ["//semgrep_rules:sca_rules"],
    target = ":main",
)

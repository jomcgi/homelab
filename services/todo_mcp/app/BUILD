load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test", "semgrep_test")

py_venv_binary(
    name = "main",
    main = "main.py",
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "app",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    rules = ["//semgrep_rules:python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

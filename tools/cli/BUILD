load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "cli",
    srcs = [
        "__init__.py",
        "auth.py",
        "knowledge_cmd.py",
        "main.py",
        "output.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//typer",
    ],
)

py_venv_binary(
    name = "main",
    srcs = ["main.py"],  # keep
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [":cli"],  # keep
)

py_test(
    name = "auth_test",
    srcs = ["auth_test.py"],
    deps = [
        ":cli",
        "@pip//pytest",
    ],
)

py_test(
    name = "output_test",
    srcs = ["output_test.py"],
    deps = [
        ":cli",
        "@pip//pytest",
    ],
)

# gazelle:resolve py knowledge //projects/monolith:monolith_backend
# gazelle:resolve py knowledge.gardener //projects/monolith:monolith_backend
# gazelle:resolve py knowledge.models //projects/monolith:monolith_backend
# gazelle:resolve py app.main //projects/monolith:monolith_backend
# gazelle:resolve py app.db //projects/monolith:monolith_backend
py_test(
    name = "knowledge_test",
    srcs = ["knowledge_test.py"],
    imports = ["../../projects/monolith"],  # keep
    deps = [
        ":cli",
        "//projects/monolith:monolith_backend",
        "@pip//fastapi",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//typer",
    ],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        ":cli",
        "@pip//pytest",
        "@pip//typer",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":main",
)

semgrep_test(
    name = "auth_test_semgrep_test",
    srcs = ["auth_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "knowledge_test_semgrep_test",
    srcs = ["knowledge_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "output_test_semgrep_test",
    srcs = ["output_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "knowledge_unit_test",
    srcs = ["knowledge_unit_test.py"],
    deps = [
        ":cli",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//typer",
    ],
)

semgrep_test(
    name = "knowledge_unit_test_semgrep_test",
    srcs = ["knowledge_unit_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

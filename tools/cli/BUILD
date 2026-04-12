load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "homelab_cli",
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
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
    deps = [":homelab_cli"],  # keep
)

py_test(
    name = "auth_test",
    srcs = ["auth_test.py"],
    deps = [
        ":cli",
        ":homelab_cli",  # keep
        "@pip//pytest",
    ],
)

py_test(
    name = "output_test",
    srcs = ["output_test.py"],
    deps = [
        ":cli",
        ":homelab_cli",  # keep
    ],
)

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
        ":homelab_cli",  # keep
        "//projects/monolith:monolith_backend",
        "@pip//fastapi",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//typer",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "auth_semgrep_test",
    srcs = ["auth.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "auth_test_semgrep_test",
    srcs = ["auth_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "knowledge_cmd_semgrep_test",
    srcs = ["knowledge_cmd.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "knowledge_test_semgrep_test",
    srcs = ["knowledge_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "output_semgrep_test",
    srcs = ["output.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "output_test_semgrep_test",
    srcs = ["output_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

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

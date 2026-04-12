load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
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
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
    imports = ["."],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//typer",
    ],
)

py_test(
    name = "auth_test",
    srcs = ["auth_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "@pip//pytest",
    ],
)

py_test(
    name = "output_test",
    srcs = ["output_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "@pip//pytest",
    ],
)

# gazelle:resolve py knowledge.gardener //projects/monolith:monolith_backend
# gazelle:resolve py knowledge.models //projects/monolith:monolith_backend
# gazelle:resolve py app.main //projects/monolith:monolith_backend
# gazelle:resolve py app.db //projects/monolith:monolith_backend
py_test(
    name = "knowledge_test",
    srcs = ["knowledge_test.py"],
    imports = ["."],
    deps = [
        ":homelab_cli",
        "//projects/monolith:monolith_backend",
        "@pip//pytest",
    ],
)

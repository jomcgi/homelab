# gazelle:resolve py auth //tools/cli:homelab_cli
# gazelle:resolve py auth.get_cf_token //tools/cli:homelab_cli
# gazelle:resolve py output //tools/cli:homelab_cli
# gazelle:resolve py output.compact_line //tools/cli:homelab_cli
# gazelle:resolve py output.format_edges //tools/cli:homelab_cli
# gazelle:resolve py output.search_line //tools/cli:homelab_cli
# gazelle:resolve py output.write_to_tmpfile //tools/cli:homelab_cli
# gazelle:resolve py knowledge_cmd //tools/cli:homelab_cli
# gazelle:resolve py knowledge_cmd.knowledge_app //tools/cli:homelab_cli
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
    srcs = ["main.py"],  # keep
    imports = ["."],  # keep
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [":homelab_cli"],  # keep
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
    imports = [".", "../../projects/monolith"],  # keep
    deps = [
        ":homelab_cli",
        "//projects/monolith:monolith_backend",
        "@pip//pytest",
    ],
)

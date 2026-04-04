load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //projects/trips/tools/backfill-elevation:backfill-elevation

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/trips/tools/elevation",
        "@pip//nats_py",
        "@pip//rich",
        "@pip//typer",
    ],
)

py_library(
    name = "backfill-elevation",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/trips/tools/elevation",
        "@pip//nats_py",
        "@pip//rich",
        "@pip//typer",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

# gazelle:resolve py main //projects/trips/tools/backfill-elevation:backfill-elevation
# gazelle:resolve py main.TripPoint //projects/trips/tools/backfill-elevation:backfill-elevation
# gazelle:resolve py main.publish_point //projects/trips/tools/backfill-elevation:backfill-elevation
# gazelle:resolve py main.replay_stream //projects/trips/tools/backfill-elevation:backfill-elevation
py_test(
    name = "backfill_elevation_test",
    srcs = ["backfill_elevation_test.py"],
    imports = ["."],
    deps = [
        "//projects/trips/tools/backfill-elevation",
        "@pip//nats_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "backfill_elevation_test_semgrep_test",
    srcs = ["backfill_elevation_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

# gazelle:resolve py main_test //projects/trips/tools/backfill-elevation:backfill-elevation
py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    imports = ["."],
    deps = [
        "//projects/trips/tools/backfill-elevation",
        "@pip//nats_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

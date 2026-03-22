load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py bazel //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload._detect_branch //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload._detect_commit //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload._detect_repo //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload._detect_semgrep_version //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload._git //bazel/tools/semgrep:semgrep
# gazelle:resolve py bazel.tools.semgrep.upload.main //bazel/tools/semgrep:semgrep

py_venv_binary(
    name = "upload",
    srcs = ["upload.py"],
    main = "upload.py",
    visibility = ["//visibility:public"],
    deps = ["@pip//httpx"],
)

py_library(
    name = "semgrep",
    srcs = ["upload.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

py_test(
    name = "upload_test",
    srcs = ["upload_test.py"],
    deps = [
        "//bazel/tools/semgrep",
        "@pip//pytest",
    ],
)

semgrep_target_test(
    name = "upload_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":upload",
)

semgrep_test(
    name = "test_upload_semgrep_test",
    srcs = ["test_upload.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

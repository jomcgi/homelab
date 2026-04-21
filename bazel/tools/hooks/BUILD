load("@rules_shell//shell:sh_test.bzl", "sh_test")

package(default_visibility = ["//visibility:public"])

exports_files(glob(["*.sh"]))

sh_test(
    name = "prefer_bb_remote_test",
    srcs = ["prefer-bb-remote_test.sh"],
    data = [":prefer-bb-remote.sh"],
)

sh_test(
    name = "check_python_file_shadows_package_test",
    srcs = ["check-python-file-shadows-package_test.sh"],
    data = [":check-python-file-shadows-package.sh"],
)

load("@rules_shell//shell:sh_test.bzl", "sh_test")

package(default_visibility = ["//visibility:public"])

exports_files(glob(["*.sh"]))

sh_test(
    name = "check_copyright_year_test",
    srcs = ["check-copyright-year_test.sh"],
    data = [":check-copyright-year.sh"],
)

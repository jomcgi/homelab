# gazelle:exclude **

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "yaml_fixtures",
    srcs = glob(["fixtures/*.yaml"]),
)

# Fixture for the stale-copyright-year rule (languages: generic).
# Referenced by //bazel/semgrep/rules:stale_copyright_year_test.
filegroup(
    name = "stale_copyright_year_fixtures",
    srcs = ["fixtures/stale-copyright-year.yaml"],
)

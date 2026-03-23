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

filegroup(
    name = "typescript_fixtures",
    srcs = glob(["fixtures/*.ts"]),
)

# Fixture for the no-stale-repo-paths rule (languages: generic).
# Referenced by //bazel/semgrep/rules:generic_rules_test.
filegroup(
    name = "no_stale_repo_paths_fixtures",
    srcs = ["fixtures/no-stale-repo-paths.md"],
)

# Fixtures for kubernetes rules (require-readiness-probe, require-resource-limits, etc.).
# Referenced by //bazel/semgrep/rules:kubernetes_rules_test.
filegroup(
    name = "kubernetes_yaml_fixtures",
    srcs = glob([
        "fixtures/require-readiness-probe.yaml",
        "fixtures/require-resource-limits.yaml",
        "fixtures/require-tmp-emptydir.yaml",
        "fixtures/no-hardcoded-image-digest.yaml",
        "fixtures/no-host-network.yaml",
        "fixtures/no-privileged.yaml",
    ]),
)

# gazelle:exclude **

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "yaml_fixtures",
    srcs = glob(
        ["fixtures/*.yaml"],
        # Exclude Go-rule reference fixtures that are not tested against yaml_rules.
        # Exclude SQL/generic and kubernetes-specific fixtures that are tested separately.
        exclude = [
            "fixtures/fastapi-bare-tuple-return.yaml",
            "fixtures/no-create-extension-sql.yaml",
            "fixtures/no-discarded-json-marshal.yaml",
            "fixtures/no-shared-preload-libraries-cnpg.yaml",
            "fixtures/require-cnpg-cluster-resources.yaml",
            "fixtures/unsafe-json-field-access.yaml",
        ],
    ),
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

# Fixture for the no-create-extension-sql rule (languages: generic, paths: **/migrations/*.sql).
# Referenced by //bazel/semgrep/rules:sql_rules_test.
filegroup(
    name = "no_create_extension_sql_fixtures",
    srcs = ["fixtures/no-create-extension-sql.yaml"],
)

# Fixtures for kubernetes rules (require-readiness-probe, require-resource-limits, etc.).
# Referenced by //bazel/semgrep/rules:kubernetes_rules_test.
# New rule fixtures should be added here as they are created.
filegroup(
    name = "kubernetes_yaml_fixtures",
    srcs = glob([
        "fixtures/no-hardcoded-image-digest.yaml",
        "fixtures/no-host-network.yaml",
        "fixtures/no-privileged.yaml",
        "fixtures/no-shared-preload-libraries-cnpg.yaml",
        "fixtures/pdb-minAvailable-blocks-eviction.yaml",
        "fixtures/require-cnpg-cluster-resources.yaml",
        "fixtures/require-fsgroup-with-pvc.yaml",
        "fixtures/require-readiness-probe.yaml",
        "fixtures/require-resource-limits.yaml",
        "fixtures/require-tmp-emptydir.yaml",
    ]),
)

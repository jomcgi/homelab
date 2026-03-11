"Define linter aspects"

load("@aspect_rules_lint//lint:eslint.bzl", "lint_eslint_aspect")
load("@aspect_rules_lint//lint:lint_test.bzl", "lint_test")
load("@aspect_rules_lint//lint:ruff.bzl", "lint_ruff_aspect")
load("@aspect_rules_lint//lint:shellcheck.bzl", "lint_shellcheck_aspect")

eslint = lint_eslint_aspect(
    binary = Label(":eslint"),
    # We trust that eslint will locate the correct configuration file for a given source file.
    # See https://eslint.org/docs/latest/use/configure/configuration-files#cascading-and-hierarchy
    configs = [
        Label("//bazel/tools/lint:eslintrc"),
        # if the repository has nested eslintrc files, they must be added here as well
    ],
)

eslint_test = lint_test(aspect = eslint)
ruff = lint_ruff_aspect(
    binary = "@multitool//tools/ruff",
    configs = [
        Label("//:pyproject.toml"),
        # if the repository has nested ruff.toml files, they must be added here as well
    ],
)

ruff_test = lint_test(aspect = ruff)

shellcheck = lint_shellcheck_aspect(
    binary = "@multitool//tools/shellcheck",
    config = Label("//bazel/tools/lint:.shellcheckrc"),
)

shellcheck_test = lint_test(aspect = shellcheck)

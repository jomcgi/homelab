# Bazel Workflows

This repository uses [Aspect Workflows](https://aspect.build) to provide a consistent developer experience for building, testing, and linting code.

## Formatting Code

The `format` command is provided by the `.envrc` file and the bazel-env.bzl setup in this repo.

```shell
# Re-format all files in the repository
format

# Re-format a single file
format path/to/file
```

**Pre-commit hook:** Run `git config core.hooksPath githooks` to automatically format files before committing.

## Linting Code

This project uses [rules_lint](https://github.com/aspect-build/rules_lint) to run linting tools via Bazel's aspects feature. Linters produce cached report files like any other Bazel action.

The Aspect CLI provides the [`lint` command](https://docs.aspect.build/cli/commands/aspect_lint) which collects report files, presents them with colored output, offers interactive fix suggestions, and returns appropriate exit codes.

```shell
# Check for lint violations across the entire repository
aspect lint //...

# Lint a specific package
aspect lint //path/to/package:all
```

## Installing Dev Tools

To make CLI tools available without manual installation:

1. Add the tool to `tools/tools.lock.json`
2. Run `bazel run //tools:bazel_env` and follow any printed instructions
3. Tools will be available on your PATH when working in the repository

See [Run Tools Installed by Bazel](https://blog.aspect.build/run-tools-installed-by-bazel) for details.

## Working with npm Packages

To install a `node_modules` tree locally for your editor or tooling outside of Bazel:

```shell
pnpm install
```

To add or remove packages, use the workspace-local pnpm to ensure consistent lockfile format:

```shell
# From any subdirectory
$(bazel info workspace)/tools/pnpm add <package-name>
```

## Working with Python Packages

After adding a new `import` statement in Python code, run `bazel run gazelle` to update the BUILD file.

If the package is not already a dependency, add it to the project:

```shell
# 1. Add the dependency to pyproject.toml
vim pyproject.toml

# 2. Update lock files to pin the dependency
./tools/repin

# 3. Update BUILD files
bazel run gazelle
```

**Console scripts:** To create a runnable binary for a console script from a third-party package:

```shell
cat<<'EOF' | buildozer -f -
new_load @rules_python//python/entry_points:py_console_script_binary.bzl py_console_script_binary|new py_console_script_binary scriptname|tools:__pkg__
set pkg "@pip//package_name_snake_case"|tools:scriptname
EOF
```

Then edit the new entry in `tools/BUILD` to replace `package_name_snake_case` with the package name and `scriptname` with the script name.

See the [py_console_script_binary documentation](https://rules-python.readthedocs.io/en/stable/api/python/entry_points/py_console_script_binary.html) for details.

## Working with Go Modules

After adding a new `import` statement in Go code, run `bazel run gazelle` to update the BUILD file.

If the package is not already a dependency, add it to the project:

```shell
# 1. Update go.mod and go.sum (uses the same Go SDK as Bazel via direnv)
go mod tidy -v

# 2. Update MODULE.bazel to include the package in use_repo
bazel mod tidy

# 3. Update BUILD files
bazel run gazelle
```

## Working with Cargo

You can run `cargo` outside of Bazel using the tool installed on the PATH:

```shell
cargo add <crate-name>
```

After adding dependencies, run `bazel run gazelle` if your project uses Gazelle for Rust.

## Stamping Release Builds

Stamping produces non-deterministic outputs by including information such as version numbers or commit hashes.

Read more: [Stamping Bazel Builds with Selective Delivery](https://blog.aspect.build/stamping-bazel-builds-with-selective-delivery)

To declare a build output which can be stamped, use a stamp-aware rule such as [expand_template](https://docs.aspect.build/rulesets/aspect_bazel_lib/docs/expand_template).

The `tools/workspace_status.sh` file provides these stamp keys:

| Key                       | Description                                               |
| ------------------------- | --------------------------------------------------------- |
| `STABLE_GIT_COMMIT`       | The commit hash of HEAD                                   |
| `STABLE_MONOREPO_VERSION` | A semver-compatible version (e.g., `2020.44.123+abc1234`) |

To request stamped build outputs, add the flag `--config=release` to your Bazel command.

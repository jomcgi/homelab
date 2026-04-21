"""Top-level conftest for BDD tests — registers the shared testing plugin.

This file must be included at the Bazel runfiles root level (via srcs in the
bdd_test macro) so pytest accepts the pytest_plugins declaration.
"""

pytest_plugins = ["shared.testing.plugin"]

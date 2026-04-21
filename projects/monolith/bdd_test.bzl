"""Macro for domain BDD test targets with shared harness pre-wired."""

load("//bazel/tools/pytest:defs.bzl", "py_test")

def bdd_test(name, srcs, playwright = False, size = "large", timeout = "moderate", **kwargs):
    """BDD test target with shared testing fixtures and data deps.

    Args:
        name: Target name.
        srcs: Test source files (include the domain's tests/conftest.py).
        playwright: If True, adds frontend_dist data dep and playwright tag.
        size: Test size (default "large" since it starts real PostgreSQL).
        timeout: Test timeout (default "moderate").
        **kwargs: Passed to py_test.
    """
    data = [
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ]
    tags = ["bdd"]

    if playwright:
        data.append("//projects/monolith:frontend_dist")
        tags.append("playwright")

    py_test(
        name = name,
        srcs = srcs,
        data = data,
        imports = ["."],
        tags = tags,
        size = size,
        timeout = timeout,
        deps = [
            "//projects/monolith:shared_testing",
            "//projects/monolith:monolith_backend",
        ] + kwargs.pop("deps", []),
        **kwargs
    )

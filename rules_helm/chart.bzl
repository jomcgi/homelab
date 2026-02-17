"""Macro for declaring Helm chart packages."""

load("//rules_helm:push.bzl", "helm_package", "helm_push")
load("//rules_helm:test.bzl", "helm_lint_test")

def helm_chart(name, publish = False, repository = "oci://ghcr.io/jomcgi/homelab/charts", source_url = "https://github.com/jomcgi/homelab", visibility = None, lint = True):
    """Declares a Helm chart directory with optional lint testing and OCI publishing.

    This macro replaces chart_files() and adds support for packaging charts as
    .tgz archives and pushing them to OCI registries.

    Args:
        name: Name of the filegroup target (typically "chart")
        publish: If True, create package and push targets for OCI registry
        repository: OCI repository URL for pushing (default: ghcr.io/jomcgi/homelab/charts)
        source_url: Base GitHub repository URL for chart deep linking (default: github.com/jomcgi/homelab)
        visibility: Visibility for the filegroup target
        lint: If True, create a helm lint test (default: True)
    """
    native.exports_files([
        "Chart.yaml",
        "values.yaml",
    ])

    native.filegroup(
        name = name,
        srcs = native.glob(["**/*"]),
        visibility = visibility,
    )

    if lint:
        helm_lint_test(
            name = "lint_test",
            tags = ["chart", "lint"],
        )

    if publish:
        helm_package(
            name = name + ".package",
            srcs = native.glob(["**/*"]),
            url = source_url + "/tree/main/" + native.package_name(),
        )

        helm_push(
            name = name + ".push",
            chart = name + ".package",
            repository = repository,
            visibility = ["//images:__pkg__"],
        )

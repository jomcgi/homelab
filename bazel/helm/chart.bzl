"""Macro for declaring Helm chart packages."""

load("//bazel/helm:images.bzl", "helm_images_values")
load("//bazel/helm:push.bzl", "helm_package", "helm_push")
load("//bazel/helm:test.bzl", "helm_lint_test")

def helm_chart(name, publish = False, repository = "oci://ghcr.io/jomcgi/homelab/charts", source_url = "https://github.com/jomcgi/homelab", visibility = None, lint = True, images = None):
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
        images: Optional dict mapping Helm values path strings to image labels.
                Each label must expose an OciImageInfo provider (produced automatically
                by go_image, apko_image, and py3_image as the "{name}.info" target).

                At build time the generated values are deep-merged into the
                chart's values.yaml, overriding the default repository and tag
                for each image path.

                Example:
                    images = {
                        "image": "//charts/todo/image:image.info",
                    }
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

    # When images are specified, generate a values YAML fragment at build time.
    # helm_images_values uses label_keyed_string_dict (label → yaml_path),
    # so we invert the user-supplied dict ({yaml_path: label}).
    images_values_target = None
    if images:
        helm_images_values(
            name = name + ".images_values",
            images = {label: yaml_path for yaml_path, label in images.items()},
        )
        images_values_target = ":" + name + ".images_values"

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
            values_overlay = images_values_target,
        )

        helm_push(
            name = name + ".push",
            chart = name + ".package",
            repository = repository,
            chart_dir = native.package_name(),
            visibility = ["//bazel/images:__pkg__"],
        )

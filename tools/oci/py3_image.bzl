"py_image"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@aspect_rules_py//py:defs.bzl", "py_image_layer")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load", "oci_push")

def py3_image(name, binary, root = "/", layer_groups = {}, env = {}, workdir = None, base = "@python_base", repository = None):
    """Create a Python 3 image from a Python binary.

    Args:
        name: The name of the image.
        binary: The Python binary to create the image from.
        root: The root directory where everything will be put into
        layer_groups: The layer groups to use for the image.
        env: The environment variables to set in the image.
        workdir: The working directory to set in the image.
        base: The base image to use for the image.
        repository: The container registry repository (e.g., "ghcr.io/jomcgi/homelab/my-app").
                   Defaults to "ghcr.io/jomcgi/homelab/{package_name}".
    """
    binary = native.package_relative_label(binary)
    binary_path = "{}{}/{}".format(root, binary.package, binary.name)
    runfiles_dir = "{}.runfiles".format(binary_path)
    repo_name = binary.repo_name or "_main"
    env = dict({
        "BAZEL_WORKSPACE": repo_name,
        "RUNFILES_DIR": runfiles_dir,
    }, **env)

    oci_image(
        name = name + "_image",
        base = base,
        tars = py_image_layer(
            name = name + "_layers",
            binary = binary,
            root = root,
            layer_groups = layer_groups,
        ),
        entrypoint = [binary_path],
        env = env,
        workdir = workdir or "{}/{}".format(runfiles_dir, repo_name),
    )
    platform_transition_filegroup(
        name = name,
        srcs = [name + "_image"],
        target_platform = select({
            "@platforms//cpu:arm64": "//tools/platforms:linux_aarch64",
            "@platforms//cpu:x86_64": "//tools/platforms:linux_x86_64",
        }),
    )
    oci_load(
        name = name + ".load",
        image = name,
        repo_tags = [
            native.package_name() + ":latest",
        ],
    )

    # Create stamped tags file with branch and timestamp tags
    expand_template(
        name = name + "_stamped_tags",
        out = name + "_stamped.tags.txt",
        template = [
            "{STABLE_BRANCH_TAG}",  # Branch name (e.g., "main", "feature-xyz")
            "{STABLE_IMAGE_TAG}",  # Timestamp: YYYY.MM.DD.HH.MM.SS-shortsha
        ],
        stamp_substitutions = {
            "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
            "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
        },
    )

    oci_push(
        name = name + ".push",
        image = name,
        repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
        remote_tags = name + "_stamped_tags",
    )

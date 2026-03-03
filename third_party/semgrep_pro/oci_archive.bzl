"""oci_archive - Fetch OCI artifacts from GHCR and extract filesystem layers."""

_GHCR_REGISTRY = "ghcr.io"

_DEFAULT_BUILD_FILE_CONTENT = """\
filegroup(
    name = "files",
    srcs = glob(["**/*"]),
    visibility = ["//visibility:public"],
)
"""

def _get_github_token(rctx):
    """Get a GitHub token from environment variables.

    Checks GHCR_TOKEN first, then GITHUB_TOKEN.

    Returns:
        The token string, or None if neither variable is set.
    """
    token = rctx.os.environ.get("GHCR_TOKEN", "")
    if token:
        return token
    token = rctx.os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    return None

def _exchange_token(rctx, github_token, image):
    """Exchange a GitHub token for a GHCR bearer token.

    Args:
        rctx: Repository context.
        github_token: GitHub personal access token or GHCR token.
        image: Image path (without registry prefix).

    Returns:
        Bearer token string.
    """
    url = "https://{registry}/token?service={registry}&scope=repository:{image}:pull".format(
        registry = _GHCR_REGISTRY,
        image = image,
    )

    result = rctx.execute(
        ["curl", "-sf", "-u", "_:" + github_token, url],
        timeout = 30,
    )

    if result.return_code != 0:
        fail("Failed to exchange GitHub token for GHCR bearer token.\n" +
             "Image: {image}\n".format(image = image) +
             "curl exit code: {code}\n".format(code = result.return_code) +
             "stderr: {err}".format(err = result.stderr))

    response = json.decode(result.stdout)
    token = response.get("token")
    if not token:
        fail("GHCR token response missing 'token' field.\nResponse: {resp}".format(resp = result.stdout))
    return token

def _fetch_manifest(rctx, bearer_token, image, digest):
    """Fetch an OCI manifest by digest.

    Args:
        rctx: Repository context.
        bearer_token: GHCR bearer token.
        image: Image path (without registry prefix).
        digest: Manifest digest (sha256:...).

    Returns:
        Decoded manifest dict.
    """
    url = "https://{registry}/v2/{image}/manifests/{digest}".format(
        registry = _GHCR_REGISTRY,
        image = image,
        digest = digest,
    )

    result = rctx.execute(
        [
            "curl",
            "-sf",
            "-H",
            "Authorization: Bearer " + bearer_token,
            "-H",
            "Accept: application/vnd.oci.image.manifest.v1+json",
            url,
        ],
        timeout = 30,
    )

    if result.return_code != 0:
        fail("Failed to fetch OCI manifest.\n" +
             "Image: {image}\n".format(image = image) +
             "Digest: {digest}\n".format(digest = digest) +
             "curl exit code: {code}\n".format(code = result.return_code) +
             "stderr: {err}".format(err = result.stderr))

    return json.decode(result.stdout)

def _archive_extension(media_type):
    """Determine file extension from OCI layer mediaType.

    Args:
        media_type: OCI mediaType string.

    Returns:
        File extension including leading dot (e.g. ".tar.gz").
    """
    if media_type.endswith("+gzip"):
        return ".tar.gz"
    if media_type.endswith("+zstd"):
        return ".tar.zst"
    return ".tar"

def _download_layer(rctx, bearer_token, image, layer_digest, output):
    """Download a layer blob from GHCR.

    Uses curl with -L to follow redirects (GHCR redirects to CDN),
    which is necessary because repository_ctx.download() sends auth
    headers on redirect, causing CDN failures.

    Args:
        rctx: Repository context.
        bearer_token: GHCR bearer token.
        image: Image path (without registry prefix).
        layer_digest: Layer blob digest.
        output: Output file path.
    """
    url = "https://{registry}/v2/{image}/blobs/{digest}".format(
        registry = _GHCR_REGISTRY,
        image = image,
        digest = layer_digest,
    )

    result = rctx.execute(
        [
            "curl",
            "-sfL",
            "-H",
            "Authorization: Bearer " + bearer_token,
            "-o",
            output,
            url,
        ],
        timeout = 600,
    )

    if result.return_code != 0:
        fail("Failed to download OCI layer blob.\n" +
             "Image: {image}\n".format(image = image) +
             "Layer digest: {digest}\n".format(digest = layer_digest) +
             "curl exit code: {code}\n".format(code = result.return_code) +
             "stderr: {err}".format(err = result.stderr))

def _oci_archive_impl(rctx):
    """Implementation of the oci_archive repository rule."""

    digest = rctx.attr.digest

    # Graceful degradation: empty digest creates an empty repo with a
    # default BUILD file. This allows initial setup before digests are known.
    if not digest:
        build_content = rctx.attr.build_file_content or _DEFAULT_BUILD_FILE_CONTENT
        rctx.file("BUILD.bazel", build_content)
        return

    # Resolve a GitHub token
    github_token = _get_github_token(rctx)
    if not github_token:
        fail(
            "oci_archive requires a GitHub token to pull from GHCR.\n" +
            "Set one of these environment variables:\n" +
            "  GHCR_TOKEN  - a GHCR personal access token (preferred)\n" +
            "  GITHUB_TOKEN - a GitHub personal access token with read:packages scope\n",
        )

    image = rctx.attr.image

    # Step 1: Exchange GitHub token for GHCR bearer token
    bearer_token = _exchange_token(rctx, github_token, image)

    # Step 2: Fetch OCI manifest by digest
    manifest = _fetch_manifest(rctx, bearer_token, image, digest)

    # Step 3: Parse layer info from manifest
    layer = manifest["layers"][0]
    layer_digest = layer["digest"]
    media_type = layer["mediaType"]
    ext = _archive_extension(media_type)
    archive_file = "layer" + ext

    # Step 4: Download the layer blob
    _download_layer(rctx, bearer_token, image, layer_digest, archive_file)

    # Step 5: Extract and clean up
    rctx.extract(
        archive = archive_file,
        stripPrefix = rctx.attr.strip_prefix,
    )
    rctx.delete(archive_file)

    # Step 6: Write BUILD file
    build_content = rctx.attr.build_file_content or _DEFAULT_BUILD_FILE_CONTENT
    rctx.file("BUILD.bazel", build_content)

oci_archive = repository_rule(
    implementation = _oci_archive_impl,
    attrs = {
        "image": attr.string(
            mandatory = True,
            doc = "GHCR image path without registry prefix (e.g. 'jomcgi/homelab/tools/semgrep-pro/engine-amd64').",
        ),
        "digest": attr.string(
            doc = "OCI manifest digest (sha256:...). Empty string creates an empty repo for graceful degradation.",
        ),
        "build_file_content": attr.string(
            doc = "Custom BUILD.bazel content for the extracted files. " +
                  "Defaults to a filegroup exposing all files.",
        ),
        "strip_prefix": attr.string(
            doc = "Directory prefix to strip from the extracted archive.",
        ),
    },
    environ = ["GITHUB_TOKEN", "GHCR_TOKEN"],
    doc = """Fetch a single OCI artifact from GHCR and extract its filesystem layer.

This repository rule implements a minimal OCI Distribution client:
1. Exchanges a GitHub token for a GHCR bearer token
2. Fetches the OCI manifest by digest
3. Downloads the layer blob (using curl -L to follow CDN redirects)
4. Extracts the tarball and generates a BUILD file

Requires either GITHUB_TOKEN or GHCR_TOKEN environment variable to be set.
If digest is empty, creates an empty repository with a default BUILD file
for graceful degradation during initial setup.

Example:

    oci_archive(
        name = "semgrep_pro_engine_amd64",
        image = "jomcgi/homelab/tools/semgrep-pro/engine-amd64",
        digest = "sha256:abc123...",
        build_file_content = '''
            filegroup(
                name = "engine",
                srcs = ["osemgrep-pro"],
                visibility = ["//visibility:public"],
            )
        ''',
    )
""",
)

"""oci_postgres - Extract PostgreSQL binaries + pgvector from an OCI image.

This repository rule takes an OCI layout directory (from oci.pull) and extracts
only the PostgreSQL binaries, pgvector extension files, and shared library
dependencies needed to run PostgreSQL in integration tests.

It parses the OCI layout's index.json and manifest to locate layers, then
extracts them using standard tools (tar/gzip) — no crane dependency needed
in the repository rule context.
"""

# PostgreSQL binaries to extract (relative paths within the image filesystem)
_PG_BINARIES = [
    "usr/lib/postgresql/16/bin/postgres",
    "usr/lib/postgresql/16/bin/initdb",
    "usr/lib/postgresql/16/bin/pg_isready",
    "usr/lib/postgresql/16/bin/pg_ctl",
]

# pgvector extension files
_PGVECTOR_FILES = [
    "usr/lib/postgresql/16/lib/vector.so",
    "usr/share/postgresql/16/extension/vector.control",
]

_BUILD_FILE_CONTENT = """\
filegroup(
    name = "postgres",
    srcs = glob(["**/*"]),
    visibility = ["//visibility:public"],
)
"""

def _child_path(parent, rel):
    """Construct a child path string from a parent path and relative path.

    Uses string concatenation to avoid issues with get_child and
    multi-segment paths across Bazel versions.

    Args:
        parent: A Bazel path object or string.
        rel: Relative path string (may contain '/').

    Returns:
        String path.
    """
    return str(parent) + "/" + rel

def _parse_oci_layout(rctx, oci_layout_dir):
    """Parse an OCI layout directory to find layer blob paths.

    Reads index.json -> manifest -> layer digests, returning the
    filesystem paths to each layer blob within the OCI layout.

    Args:
        rctx: Repository context.
        oci_layout_dir: String path to the OCI layout directory.

    Returns:
        List of string paths to layer blob files (gzipped tarballs).
    """

    # Read index.json to find the manifest digest
    index_content = rctx.read(rctx.path(_child_path(oci_layout_dir, "index.json")))
    index = json.decode(index_content)

    manifests = index.get("manifests", [])
    if not manifests:
        fail("OCI index.json has no manifests")

    manifest_digest = manifests[0]["digest"]

    # Digest format is "sha256:abc123..." — convert to blob path
    algo, hex_digest = manifest_digest.split(":", 1)
    manifest_blob = _child_path(oci_layout_dir, "blobs/" + algo + "/" + hex_digest)

    # Read the manifest to find layer digests
    manifest_content = rctx.read(rctx.path(manifest_blob))
    manifest = json.decode(manifest_content)

    layers = manifest.get("layers", [])
    if not layers:
        fail("OCI manifest has no layers")

    layer_paths = []
    for layer in layers:
        layer_digest = layer["digest"]
        layer_algo, layer_hex = layer_digest.split(":", 1)
        layer_path = _child_path(oci_layout_dir, "blobs/" + layer_algo + "/" + layer_hex)
        layer_paths.append(layer_path)

    return layer_paths

def _extract_layers(rctx, layer_paths, output_dir):
    """Extract all OCI layers into a single output directory.

    Layers are applied in order (first to last), matching how container
    runtimes build the filesystem.

    Args:
        rctx: Repository context.
        layer_paths: List of string paths to layer blob files.
        output_dir: String path to extract into.
    """
    for layer_path in layer_paths:
        result = rctx.execute(
            ["tar", "xzf", layer_path, "-C", output_dir],
            timeout = 120,
        )

        # Some layers may use different compression or have whiteout files;
        # tar may return warnings but still succeed. Only fail on real errors.
        if result.return_code != 0:
            # Try without gzip in case it's an uncompressed tar
            result = rctx.execute(
                ["tar", "xf", layer_path, "-C", output_dir],
                timeout = 120,
            )
            if result.return_code != 0:
                fail("Failed to extract OCI layer: {path}\nstderr: {err}".format(
                    path = layer_path,
                    err = result.stderr,
                ))

def _copy_postgres_files(rctx, staging_dir):
    """Copy only the needed PostgreSQL files from the staging directory.

    Selectively copies PG binaries, pgvector extension files, and shared
    libraries — leaving behind the rest of the image filesystem.

    Args:
        rctx: Repository context.
        staging_dir: String path to the fully extracted image filesystem.
    """
    repo_dir = str(rctx.path(""))

    # Copy specific binaries and pgvector files
    for rel_path in _PG_BINARIES + _PGVECTOR_FILES:
        src = _child_path(staging_dir, rel_path)
        dest = _child_path(repo_dir, rel_path)

        # Ensure parent directory exists
        parent_dir = dest.rsplit("/", 1)[0]
        result = rctx.execute(["mkdir", "-p", parent_dir], timeout = 10)
        if result.return_code != 0:
            fail("Failed to create directory {dir}: {err}".format(
                dir = parent_dir,
                err = result.stderr,
            ))
        result = rctx.execute(["cp", "-a", src, dest], timeout = 10)
        if result.return_code != 0:
            fail("Failed to copy {path}: {err}".format(
                path = rel_path,
                err = result.stderr,
            ))

    # Copy pgvector SQL migration files (glob pattern: vector--*.sql)
    sql_src_dir = _child_path(staging_dir, "usr/share/postgresql/16/extension")
    sql_dest_dir = _child_path(repo_dir, "usr/share/postgresql/16/extension")
    rctx.execute(["mkdir", "-p", sql_dest_dir], timeout = 10)

    result = rctx.execute(
        ["find", sql_src_dir, "-maxdepth", "1", "-name", "vector--*.sql"],
        timeout = 10,
    )
    if result.return_code != 0:
        fail("Failed to find pgvector SQL files: {err}".format(err = result.stderr))
    sql_files = [f for f in result.stdout.strip().split("\n") if f]
    if not sql_files:
        fail("No pgvector SQL migration files found in {dir}".format(dir = sql_src_dir))
    for sql_file in sql_files:
        cp_result = rctx.execute(["cp", "-a", sql_file, sql_dest_dir + "/"], timeout = 10)
        if cp_result.return_code != 0:
            fail("Failed to copy pgvector SQL file {f}: {err}".format(
                f = sql_file,
                err = cp_result.stderr,
            ))

    # Copy shared libraries that PostgreSQL needs at runtime.
    # Debian-based images store .so files under usr/lib/x86_64-linux-gnu/
    # rather than directly under usr/lib/, so we search recursively.
    lib_src = _child_path(staging_dir, "usr/lib")
    lib_dest = _child_path(repo_dir, "usr/lib")
    rctx.execute(["mkdir", "-p", lib_dest], timeout = 10)

    result = rctx.execute(
        ["find", lib_src, "-name", "*.so*", "!", "-type", "d"],
        timeout = 30,
    )
    if result.return_code != 0:
        fail("Failed to find shared libraries in {dir}: {err}".format(
            dir = lib_src,
            err = result.stderr,
        ))
    so_files = [f for f in result.stdout.strip().split("\n") if f]
    if not so_files:
        fail("No shared libraries (.so*) found in {dir} — PostgreSQL will fail at runtime".format(dir = lib_src))
    for so_file in so_files:
        rctx.execute(["cp", "-aL", so_file, lib_dest + "/"], timeout = 10)

    # Copy the postgresql lib directory (contains internal .so files)
    pg_lib_src = _child_path(staging_dir, "usr/lib/postgresql/16/lib")
    pg_lib_dest = _child_path(repo_dir, "usr/lib/postgresql/16/lib")
    rctx.execute(["mkdir", "-p", pg_lib_dest], timeout = 10)
    result = rctx.execute(["cp", "-a", "-R", pg_lib_src + "/.", pg_lib_dest + "/"], timeout = 30)
    if result.return_code != 0:
        fail("Failed to copy postgresql lib directory: {err}".format(err = result.stderr))

    # Copy the postgresql share directory (timezone, locale, SQL configs)
    pg_share_src = _child_path(staging_dir, "usr/share/postgresql/16")
    pg_share_dest = _child_path(repo_dir, "usr/share/postgresql/16")
    rctx.execute(["mkdir", "-p", pg_share_dest], timeout = 10)
    result = rctx.execute(["cp", "-a", "-R", pg_share_src + "/.", pg_share_dest + "/"], timeout = 30)
    if result.return_code != 0:
        fail("Failed to copy postgresql share directory: {err}".format(err = result.stderr))

def _oci_postgres_impl(rctx):
    """Implementation of the oci_postgres repository rule."""

    # Resolve the OCI layout directory from the label.
    # The label points to index.json inside the OCI layout repo;
    # we use .dirname to get the layout directory itself.
    oci_layout_dir = str(rctx.path(rctx.attr.image).dirname)

    # Step 1: Parse OCI layout to find layer blobs
    layer_paths = _parse_oci_layout(rctx, oci_layout_dir)

    # Step 2: Extract all layers into a staging directory
    staging_dir = str(rctx.path("_staging"))
    rctx.execute(["mkdir", "-p", staging_dir], timeout = 10)
    _extract_layers(rctx, layer_paths, staging_dir)

    # Step 3: Copy only the PostgreSQL files we need
    _copy_postgres_files(rctx, staging_dir)

    # Step 4: Clean up the staging directory
    rctx.execute(["rm", "-rf", staging_dir], timeout = 60)

    # Step 5: Write BUILD file
    rctx.file("BUILD.bazel", _BUILD_FILE_CONTENT)

oci_postgres = repository_rule(
    implementation = _oci_postgres_impl,
    attrs = {
        "image": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "Label pointing to index.json in the OCI layout from oci.pull (e.g. @pgvector_pg16_linux_amd64//:index.json).",
        ),
    },
    doc = """Extract PostgreSQL binaries and pgvector extension from an OCI image.

This repository rule parses an OCI layout directory (produced by oci.pull),
extracts all image layers, and copies out only the PostgreSQL binaries,
pgvector extension files, and shared library dependencies needed to run
PostgreSQL in integration tests.

The extracted files are exposed as a single filegroup target.

Example:

    oci_postgres(
        name = "postgres_test",
        image = "@pgvector_pg16_linux_amd64//:index.json",
    )

Then depend on it in tests:

    py_test(
        name = "my_e2e_test",
        data = ["@postgres_test//:postgres"],
    )
""",
)

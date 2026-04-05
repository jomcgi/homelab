"""Module extension for PostgreSQL + pgvector OCI extraction.

Registers the oci_postgres repository rule as a Bazel module extension,
extracting PostgreSQL 16 binaries and pgvector from the pulled OCI image
for use as test data dependencies.
"""

load(":oci_postgres.bzl", "oci_postgres")

def _postgres_ext_impl(module_ctx):
    oci_postgres(
        name = "postgres_test",
        image = "@pgvector_pg16_linux_amd64//:index.json",
    )

postgres = module_extension(implementation = _postgres_ext_impl)

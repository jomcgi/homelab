load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

# Postgres OCI extraction rule and module extension.
# Used to extract PostgreSQL binaries + pgvector from an OCI image
# for use as test data dependencies in e2e integration tests.

bzl_library(
    name = "extensions",
    srcs = ["extensions.bzl"],
    visibility = ["//visibility:public"],
    deps = [":oci_postgres"],
)

bzl_library(
    name = "oci_postgres",
    srcs = ["oci_postgres.bzl"],
    visibility = ["//visibility:public"],
)

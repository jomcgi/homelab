"""Module extension for Semgrep Pro OCI artifacts.

Creates repository rules for the pro engine (per-platform) and
per-language rule packs. Reads digest pins from digests.bzl.
"""

load(":digests.bzl", "SEMGREP_PRO_DIGESTS")
load(":oci_archive.bzl", "oci_archive")

_GHCR_PREFIX = "jomcgi/homelab/tools/semgrep-pro"

_ENGINE_BUILD = """\
filegroup(
    name = "engine",
    srcs = glob(["semgrep-core-proprietary"], allow_empty = True),
    visibility = ["//visibility:public"],
)
"""

_RULES_BUILD = """\
filegroup(
    name = "rules",
    srcs = glob(["*.yaml"], allow_empty = True),
    visibility = ["//visibility:public"],
)
"""

def _semgrep_pro_impl(module_ctx):
    # Engine binary — one repo per platform (Linux)
    for platform in ["amd64", "arm64"]:
        oci_archive(
            name = "semgrep_pro_engine_" + platform,
            image = _GHCR_PREFIX + "/engine-" + platform,
            digest = SEMGREP_PRO_DIGESTS.get("engine_" + platform, ""),
            build_file_content = _ENGINE_BUILD,
        )

    # Engine binary — macOS
    for platform in ["osx_arm64", "osx_x86_64"]:
        oci_archive(
            name = "semgrep_pro_engine_" + platform,
            image = _GHCR_PREFIX + "/engine-" + platform.replace("_", "-"),
            digest = SEMGREP_PRO_DIGESTS.get("engine_" + platform, ""),
            build_file_content = _ENGINE_BUILD,
        )

    # Rule packs — one repo per language
    for lang in ["golang", "python", "javascript", "kubernetes"]:
        oci_archive(
            name = "semgrep_pro_rules_" + lang,
            image = _GHCR_PREFIX + "/rules-" + lang,
            digest = SEMGREP_PRO_DIGESTS.get("rules_" + lang, ""),
            build_file_content = _RULES_BUILD,
        )

    # SCA advisory rules — vendored from Semgrep registry
    oci_archive(
        name = "semgrep_sca_rules",
        image = _GHCR_PREFIX + "/rules-sca",
        digest = SEMGREP_PRO_DIGESTS.get("rules_sca", ""),
        build_file_content = _RULES_BUILD,
    )

semgrep_pro = module_extension(implementation = _semgrep_pro_impl)

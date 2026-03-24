load("@rules_shell//shell:sh_test.bzl", "sh_test")

package(default_visibility = ["//visibility:public"])

exports_files(glob(["*.sh"]))

sh_test(
    name = "check_copyright_year_test",
    srcs = ["check-copyright-year_test.sh"],
    data = [":check-copyright-year.sh"],
)

sh_test(
    name = "prefer_argocd_mcp_test",
    srcs = ["prefer-argocd-mcp_test.sh"],
    data = [":prefer-argocd-mcp.sh"],
)

sh_test(
    name = "prefer_bb_remote_test",
    srcs = ["prefer-bb-remote_test.sh"],
    data = [":prefer-bb-remote.sh"],
)

sh_test(
    name = "prefer_k8s_mcp_test",
    srcs = ["prefer-k8s-mcp_test.sh"],
    data = [":prefer-k8s-mcp.sh"],
)

sh_test(
    name = "check_chart_version_sync_test",
    srcs = ["check-chart-version-sync_test.sh"],
    data = [":check-chart-version-sync.sh"],
)

sh_test(
    name = "check_stale_repo_paths_test",
    srcs = ["check-stale-repo-paths_test.sh"],
    data = [":check-stale-repo-paths.sh"],
)

sh_test(
    name = "check_hardcoded_svc_url_test",
    srcs = ["check-hardcoded-svc-url_test.sh"],
    data = [":check-hardcoded-svc-url.sh"],
)

sh_test(
    name = "check_library_version_bump_test",
    srcs = ["check-library-version-bump_test.sh"],
    data = [":check-library-version-bump.sh"],
)

sh_test(
    name = "check_mcp_run_http_test",
    srcs = ["check-mcp-run-http_test.sh"],
    data = [":check-mcp-run-http.sh"],
)

sh_test(
    name = "check_ebpf_otel_annotations_test",
    srcs = ["check-ebpf-otel-annotations_test.sh"],
    data = [":check-ebpf-otel-annotations.sh"],
)

sh_test(
    name = "check_empty_1password_itempath_test",
    srcs = ["check-empty-1password-itempath_test.sh"],
    data = [":check-empty-1password-itempath.sh"],
)

sh_test(
    name = "check_pdb_single_replica_test",
    srcs = ["check-pdb-single-replica_test.sh"],
    data = [":check-pdb-single-replica.sh"],
)

sh_test(
    name = "check_missing_imageupdater_test",
    srcs = ["check-missing-imageupdater_test.sh"],
    data = [":check-missing-imageupdater.sh"],
)

sh_test(
    name = "check_valuesobject_overrides_test",
    srcs = ["check-valuesobject-overrides_test.sh"],
    data = [":check-valuesobject-overrides.sh"],
)

sh_test(
    name = "check_missing_argocd_app_build_test",
    srcs = ["check-missing-argocd-app-build_test.sh"],
    data = [":check-missing-argocd-app-build.sh"],
)

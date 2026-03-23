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

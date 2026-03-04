"""Public API for rules_semgrep — Bazel rules for running semgrep scans."""

load("//rules_semgrep:target_test.bzl", _semgrep_target_test = "semgrep_target_test")
load("//rules_semgrep:test.bzl", _semgrep_manifest_test = "semgrep_manifest_test", _semgrep_test = "semgrep_test")

semgrep_test = _semgrep_test
semgrep_target_test = _semgrep_target_test
semgrep_manifest_test = _semgrep_manifest_test

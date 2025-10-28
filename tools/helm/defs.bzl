"""Public API for Helm Bazel rules.

This module provides rules for rendering and diffing Helm charts in Bazel.
These rules are designed to work with ArgoCD Application manifests and can
be auto-generated using the Gazelle extension.

Example usage:
    load("//tools/helm:defs.bzl", "helm_render", "helm_diff_script")

    helm_render(
        name = "render",
        chart = "//charts/n8n:Chart.yaml",
        release_name = "n8n",
        namespace = "n8n",
        values = [
            "//charts/n8n:values.yaml",
            "values.yaml",
        ],
    )

    helm_diff_script(
        name = "diff",
        rendered = ":render",
        namespace = "n8n",
    )
"""

load("//tools/helm/private:render.bzl", _helm_render = "helm_render")
load("//tools/helm/private:diff.bzl", _helm_diff_script = "helm_diff_script")

# Re-export rules
helm_render = _helm_render
helm_diff_script = _helm_diff_script
